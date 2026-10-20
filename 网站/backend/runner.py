"""Task execution and durable scientific outputs."""

from __future__ import annotations

import csv
import functools
import hashlib
import io
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Callable

import numpy as np

from .config import validate_simulation_config, validate_targets
from .checkpoint import (CheckpointStore, _atomic_replace, _replace_bytes, engine_environment_fingerprint,
                         precheck_checkpoint, sha256_file)
from .strict_ga import _apply_scientific_settings, run_strict_stage, scientific_settings
from .scientific_outputs import (METRIC_NAMES, PARAMETER_NAMES,
                                 actual_surface_metrics, export_compatibility_npz)
from corrosion_model.ga_优化版 import GAConfig, run_ga
from corrosion_model.ca_优化版 import first_metal_depth
from corrosion_model.fitness_优化版 import _fitness_worker_init as _engine_worker_init
from .system_info import current_memory_bytes, runtime_provenance


def _atomic_npz(path: Path, **arrays) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("wb") as stream:
            np.savez_compressed(stream, **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        _atomic_replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _replace_bytes(path, json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False).encode("utf-8"))


def _read_stage(path: Path):
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key].copy() for key in data.files}


def freeze_spec(spec: dict) -> dict:
    frozen = {"config": spec["config"], "targets": spec["targets"], "run_mode": spec["run_mode"]}
    for key in ("target_source", "target_options", "source", "source_metadata", "target_source_metadata"):
        if key in spec:
            frozen[key] = spec[key]
    return frozen


def fingerprint_config(spec: dict) -> str:
    return hashlib.sha256(json.dumps(freeze_spec(spec), ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode("utf-8")).hexdigest()


def _stage_manifest(path: Path, fingerprint: str, engine_fingerprint: str) -> dict | None:
    manifest_path = path.with_suffix(".manifest.json")
    if not manifest_path.exists():
        if path.exists():
            try:
                with np.load(path, allow_pickle=False) as arrays:
                    if str(arrays["task_fingerprint"]) != fingerprint:
                        raise ValueError("已完成阶段配置与当前任务不一致")
                    if str(arrays["engine_fingerprint"]) != engine_fingerprint:
                        raise ValueError("已完成阶段引擎或环境与当前任务不一致")
            except (KeyError, OSError, EOFError) as exc:
                raise ValueError("阶段文件缺少完整来源校验，不能安全恢复") from exc
        return None  # A complete strict checkpoint can regenerate this unpublished file.
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("阶段导出记录损坏，不能安全恢复") from exc
    if manifest.get("fingerprint") != fingerprint:
        raise ValueError("已完成阶段配置与当前任务不一致")
    if manifest.get("engine_fingerprint") != engine_fingerprint:
        raise ValueError("已完成阶段引擎或环境与当前任务不一致")
    if not path.is_file() or sha256_file(path) != manifest.get("sha256"):
        raise ValueError("已完成阶段数值文件丢失或损坏，不能安全恢复")
    return manifest


def precheck_resume(spec: dict, job_dir: Path) -> dict:
    """Read-only binding/integrity check used before spawning a resumed worker."""
    config = validate_simulation_config(spec["config"])
    validate_targets(spec["targets"], spec["run_mode"])
    if config["mode"] not in {"strict", "pycharm"}:
        raise ValueError("Taichi 高速模式不提供阶段恢复；请创建新任务")
    fingerprint = fingerprint_config(spec)
    engine = engine_environment_fingerprint()
    request_path = Path(job_dir) / "request.json"
    if request_path.exists():
        old = json.loads(request_path.read_text(encoding="utf-8"))
        if fingerprint_config(old) != fingerprint:
            raise ValueError("已冻结任务配置或目标来源与当前任务不一致")
        if old.get("engine_fingerprint") not in {None, engine}:
            raise ValueError("已冻结任务引擎或环境与当前任务不一致")
    stages = []
    for index in range(1, len(spec["targets"]) + 1):
        path = Path(job_dir) / "outputs" / f"stage_{index:03d}.npz"
        manifest = _stage_manifest(path, fingerprint, engine)
        check = precheck_checkpoint(Path(job_dir) / "checkpoints" / f"stage_{index:03d}",
                                    fingerprint, engine_fingerprint=engine)
        check.update(stage=index, stage_exported=manifest is not None)
        stages.append(check)
    return {"available": any(stage["available"] or stage["stage_exported"] for stage in stages),
            "fingerprint": fingerprint, "engine_fingerprint": engine, "stages": stages}


def _configured_worker_init(config, *args):
    """Spawned fitness workers must use the frozen task's scientific settings."""
    _apply_scientific_settings(config)
    _engine_worker_init(*args)
    if len(args) > 11 and args[11]:
        from corrosion_model.taichi_accel_优化版 import taichi_available, taichi_last_error
        if not taichi_available():
            raise RuntimeError("工作进程 Taichi 初始化失败：" + str(taichi_last_error()))


def _plot_stage(path: Path, a: np.ndarray, space_xy: float, space_z: float, cmap: str,
                *, figure_config: dict | None = None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for font_name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC"):
        if font_name in {item.name for item in font_manager.fontManager.ttflist}:
            plt.rcParams["font.sans-serif"] = [font_name]
            break

    depth = (first_metal_depth(a, a.shape[0], a.shape[1], a.shape[2]) - 1) * space_z
    figure_config = figure_config or {}
    fig, ax = plt.subplots(figsize=figure_config.get("auto_heatmap_figsize", (7, 4.5)))
    try:
        image = ax.imshow(depth.T, origin="lower", cmap=cmap, aspect="auto",
                          extent=(0, a.shape[0] * space_xy / 1000, 0, a.shape[1] * space_xy / 1000))
        ax.set(xlabel="X / mm", ylabel="Y / mm", title="首次金属层深度 / μm")
        fig.colorbar(image, ax=ax, label="μm")
        fig.tight_layout()
        fig.savefig(path, dpi=int(figure_config.get("auto_plot_dpi", 160)))
    finally:
        plt.close(fig)


def run_simulation(spec: dict, job_dir: Path, progress: Callable[[dict], None] | None = None) -> dict:
    config = validate_simulation_config(spec["config"])
    targets = spec["targets"]
    validate_targets(targets, spec["run_mode"])
    actual_backend = "NumPy ProcessPool" if config["mode"] == "pycharm" else "NumPy"
    if config["mode"] == "fast" and config["TAICHI_CONFIG"]["use_taichi"]:
        try:
            import taichi  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("高速模式已选择 Taichi，但当前 Python 未安装 taichi") from exc
        from corrosion_model.taichi_accel_优化版 import init_taichi, taichi_last_error
        if not init_taichi(str(config["TAICHI_CONFIG"]["arch"])):
            raise RuntimeError("Taichi 初始化失败：" + str(taichi_last_error()))
        actual_backend = "Taichi"
    job_dir = Path(job_dir)
    started = time.perf_counter()
    if config["mode"] in {"strict", "pycharm"}:
        precheck_resume(spec, job_dir)
    output = job_dir / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    frozen = freeze_spec(spec)
    fingerprint = fingerprint_config(spec)
    engine_fingerprint = engine_environment_fingerprint()
    provenance = runtime_provenance()
    frozen.update(fingerprint=fingerprint, engine_fingerprint=engine_fingerprint)
    _atomic_json(job_dir / "request.json", frozen)
    _atomic_json(output / "effective_config.json", frozen)
    stage_paths = []
    summaries = []
    geometry = config["GEOMETRY_CONFIG"]
    settings = config["SINGLE_STAGE_GA_CONFIG" if spec["run_mode"] == "single" else "STAGE_GA_CONFIG"]
    ga_settings = config["GA_CONFIG"]
    previous = None
    warnings = []
    timing = {"reading_seconds": float(spec.get("reading_seconds", 0)),
              "compute_seconds": 0.0, "checkpoint_seconds": 0.0,
              "export_seconds": 0.0, "plotting_seconds": 0.0,
              "postprocess_seconds": 0.0, "peak_memory_bytes": None}
    if config["mode"] == "fast":
        warnings.append("高速模式沿用原GA；不提供逐个体检查点及严格中断恢复。")
        if settings.get("reuse_process_pool", False):
            warnings.append("当前GA阶段启用跨代复用进程池；阶段结束或异常时关闭worker池。")
    elif config["mode"] == "pycharm":
        workers = int(settings["parallel_workers"])
        reuse_pool = bool(settings.get("reuse_process_pool", False))
        pool_note = "；GA阶段内跨代复用worker" if reuse_pool else "；每代重建worker池"
        warnings.append(f"PyCharm模式使用 NumPy ProcessPool，多进程数={workers}{pool_note}；每代及已完成个体评价保存检查点，未保存个体按原种子重算。")

    def timing_doc():
        document = dict(timing)
        for key in ("reading_seconds", "compute_seconds", "checkpoint_seconds", "export_seconds"):
            document[key] += sum(value for name, value in timing.items()
                                 if name.startswith("stage_") and name.endswith("_" + key))
        document["session_seconds"] = time.perf_counter() - started
        document["peak_memory_bytes"] = current_memory_bytes()
        document["scope_note"] = "阶段计算/检查点时间含可恢复历史；session_seconds仅本次进程，读取包含已冻结输入读取。"
        return document

    def emit(phase, **changes):
        if progress is not None:
            progress({"phase": phase, "total_stages": len(targets),
                      "timing": timing_doc(), **changes})

    def persist_summaries():
        _atomic_json(output / "timing.json", timing_doc())
        _atomic_json(output / "summary.json", {
            "mode": config["mode"], "run_mode": spec["run_mode"], "actual_backend": actual_backend,
            "seed": int(ga_settings["seed"]), "stages": summaries,
            "simulation_seconds": round(time.perf_counter() - started, 3),
            "timing": timing_doc(), "warnings": warnings,
            "fingerprint": fingerprint, "engine_fingerprint": engine_fingerprint,
            "objective_rule": "六指标相对误差绝对值先舍入至2位；去除第5项；第4/6项按0.6/0.4合并；四项按0.1/0.3/0.2/0.4加权。全局最优更新仍比较四项之和。",
            "metric_note": "实际六指标使用原CA形貌后处理；无法定义的分布参数为null附原因，原GA内部回退不改变。",
            "compatibility_export": "逐阶段流式ZIP/NPY导出，避免所有阶段体数组同时驻留内存；会重复读取已保存阶段。",
            "provenance": provenance,
        })
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(["stage", *["target_" + name for name in METRIC_NAMES],
                         *["actual_" + name for name in METRIC_NAMES],
                         "error_mean", "error_nonuniform", "error_mu_ratio", "error_depth_combined",
                         *PARAMETER_NAMES, "metric_notes"])
        for summary in summaries:
            writer.writerow([summary["stage"], *summary["target"], *summary["actual_six_metrics"],
                             *summary["four_errors"], *summary["parameters"].values(),
                             json.dumps(summary["metric_notes"], ensure_ascii=False)])
        _replace_bytes(output / "stage_metrics.csv", buffer.getvalue().encode("utf-8-sig"))

    persist_summaries()
    for index, row in enumerate(targets, start=1):
        stage_file = output / f"stage_{index:03d}.npz"
        read_started = time.perf_counter()
        manifest = (_stage_manifest(stage_file, fingerprint, engine_fingerprint)
                    if config["mode"] in {"strict", "pycharm"} else None)
        if manifest is not None:
            result = _read_stage(stage_file)
            timing["reading_seconds"] += time.perf_counter() - read_started
            summary = manifest["summary"]
            for name, value in manifest.get("timing", {}).items():
                timing[name] = value
        else:
            timing["reading_seconds"] += time.perf_counter() - read_started
            emit("compute", stage=index, generation=1, maxgen=int(settings["maxgen"]),
                 completed_individuals=0, total_individuals=int(settings["nind"]))
            if config["mode"] == "strict":
                def stage_progress(event):
                    if event["phase"] == "generation_completed":
                        export_started = time.perf_counter()
                        _replace_bytes(output / f"stage_{index:03d}_convergence.csv",
                                       (job_dir / "checkpoints" / f"stage_{index:03d}" /
                                        "convergence.csv").read_bytes())
                        timing["export_seconds"] += time.perf_counter() - export_started
                        _atomic_json(output / "timing.json", timing_doc())
                    event["timing"] = timing_doc()
                    event["total_stages"] = len(targets)
                    event["maxgen"] = int(settings["maxgen"])
                    if progress is not None:
                        progress(event)
                stage = run_strict_stage(
                    np.asarray(row, dtype=np.float64), config, index,
                    job_dir / "checkpoints" / f"stage_{index:03d}", fingerprint,
                    a_input=None if previous is None else previous["perfect_a"],
                    d_input=None if previous is None else previous["perfect_d"],
                    cl_input=None if previous is None else previous["perfect_cl"],
                    progress=stage_progress, run_mode=spec["run_mode"],
                    timing=timing, engine_fingerprint=engine_fingerprint,
                )
            else:
                options = GAConfig(
                    nind=int(settings["nind"]), selected_count=int(settings["selected_count"]),
                    maxgen=int(settings["maxgen"]), parallel_workers=int(settings["parallel_workers"]),
                    bits_per_param=int(ga_settings["bits_per_param"]),
                    base_px=float(ga_settings["base_px"]), base_pm=float(ga_settings["base_pm"]),
                    decay_rate=float(ga_settings["decay_rate"]), sigma_share=float(ga_settings["sigma_share"]),
                )
                import corrosion_model.fitness_优化版 as fitness_module
                original_initializer = fitness_module._fitness_worker_init
                original_executor = fitness_module.ProcessPoolExecutor
                pool_scope = None
                if settings.get("reuse_process_pool", False) and int(settings["parallel_workers"]) > 1:
                    from .benchmark_pool import ExecutorScope
                    pool_scope = ExecutorScope(original_executor, "persistent")
                    fitness_module.ProcessPoolExecutor = pool_scope
                fitness_module._fitness_worker_init = functools.partial(_configured_worker_init, config)
                compute_started = time.perf_counter()
                def ga_progress(message):
                    """将现有 GA 文本进度转成网页可读的结构化进度。"""
                    generation_match = re.search(r"Gen(\d+)", message)
                    individual_match = re.search(r"已完成\s+(\d+)\s*/\s*(\d+)\s+个体", message)
                    changes = {"stage": index, "maxgen": int(settings["maxgen"]),
                               "label": message}
                    if generation_match:
                        changes["generation"] = int(generation_match.group(1))
                    if individual_match:
                        changes["completed_individuals"] = int(individual_match.group(1))
                        changes["total_individuals"] = int(individual_match.group(2))
                    emit("compute", **changes)
                try:
                    with scientific_settings(config):
                        stage = run_ga(
                            int(geometry["grid_w"]), int(geometry["grid_l"]), int(geometry["grid_n"]),
                            float(row[0]), np.asarray(row, dtype=np.float64),
                            None if previous is None else previous["perfect_a"], int(settings["F"]),
                            index, float(geometry["space_z_um"]),
                            None if previous is None else previous["perfect_d"],
                            None if previous is None else previous["perfect_cl"],
                            seed=int(ga_settings["seed"]) + index - 1, config=options,
                            lb=np.asarray(config["GA_PARAMETER_LOWER_BOUNDS"]),
                            ub=np.asarray(config["GA_PARAMETER_UPPER_BOUNDS"]),
                            use_taichi=bool(config["TAICHI_CONFIG"]["use_taichi"]),
                            parallel_workers=int(settings["parallel_workers"]),
                            allow_taichi_parallel=bool(config["TAICHI_CONFIG"]["allow_taichi_parallel"]),
                            taichi_arch=str(config["TAICHI_CONFIG"]["arch"]),
                            verbose=ga_progress,
                            checkpoint=CheckpointStore(
                                job_dir / "checkpoints" / f"stage_{index:03d}", fingerprint,
                                engine_fingerprint=engine_fingerprint,
                            ) if config["mode"] == "pycharm" else None,
                        )
                finally:
                    fitness_module._fitness_worker_init = original_initializer
                    fitness_module.ProcessPoolExecutor = original_executor
                    if pool_scope is not None:
                        pool_scope.close()
                timing["compute_seconds"] += time.perf_counter() - compute_started
            result = {
                "perfect_result": stage.perfect_result,
                "perfect_parameter": stage.perfect_parameter,
                "perfect_a": stage.perfect_a,
                "perfect_d": stage.perfect_d,
                "perfect_cl": stage.perfect_cl,
                "generations": np.asarray(stage.generations),
                "task_fingerprint": np.asarray(fingerprint),
                "engine_fingerprint": np.asarray(engine_fingerprint),
            }
            del stage
            emit("stage_export", stage=index)
            export_started = time.perf_counter()
            _atomic_npz(stage_file, **result)
            timing["export_seconds"] += time.perf_counter() - export_started
            post_started = time.perf_counter()
            actual_metrics, metric_notes = actual_surface_metrics(result["perfect_a"], config)
            timing["postprocess_seconds"] += time.perf_counter() - post_started
            convergence = []
            if config["mode"] == "strict":
                checkpoint = CheckpointStore(job_dir / "checkpoints" / f"stage_{index:03d}",
                                             fingerprint, engine_fingerprint=engine_fingerprint)
                state = checkpoint.load()
                convergence = state["convergence"]
                _replace_bytes(output / f"stage_{index:03d}_convergence.csv",
                               (checkpoint.folder / "convergence.csv").read_bytes())
                if checkpoint.recovered_from_previous:
                    warnings.append(f"阶段{index}使用前一有效检查点恢复。")
            summary = {
                "stage": index, "target": row, "target_metrics": dict(zip(METRIC_NAMES, row)),
                "actual_metrics": actual_metrics, "actual_six_metrics": [actual_metrics[name] for name in METRIC_NAMES],
                "metric_notes": metric_notes, "four_errors": result["perfect_result"].tolist(),
                "parameters": dict(zip(PARAMETER_NAMES, result["perfect_parameter"].tolist())),
                "generations": int(result["generations"]), "convergence": convergence,
                "state_file": stage_file.name, "plot_file": f"stage_{index:03d}.png",
                "plot_available": False,
            }
            _atomic_json(stage_file.with_suffix(".manifest.json"), {
                "fingerprint": fingerprint, "engine_fingerprint": engine_fingerprint,
                "sha256": sha256_file(stage_file), "summary": summary,
                "timing": {name: value for name, value in timing.items() if name.startswith(f"stage_{index}_")},
            })
        # Only the preceding physical state and the current state coexist while
        # applying the scientific stage transition; all older volumes stay on disk.
        previous = result
        stage_paths.append(stage_file)
        summaries.append(summary)
        persist_summaries()
        emit("plot", stage=index, stages_completed=index)
        plot_started = time.perf_counter()
        try:
            _plot_stage(output / f"stage_{index:03d}.png", result["perfect_a"],
                        float(geometry["space_xy_um"]), float(geometry["space_z_um"]),
                        str(config["FIGURE_CONFIG"]["surface_cmap"]),
                        figure_config=config["FIGURE_CONFIG"])
            summary["plot_available"] = True
        except Exception as exc:
            warnings.append(f"阶段{index}绘图失败：{exc}")
        finally:
            timing["plotting_seconds"] += time.perf_counter() - plot_started
        persist_summaries()
        emit("stage_completed", stage=index, stages_completed=index,
             generation=summary["generations"], maxgen=int(settings["maxgen"]),
             completed_individuals=int(settings["nind"]),
             total_individuals=int(settings["nind"]))
    previous = None
    del result
    emit("final_export", stages_completed=len(stage_paths))
    export_started = time.perf_counter()
    export_compatibility_npz(output / "simulation.npz", stage_paths)
    timing["export_seconds"] += time.perf_counter() - export_started
    persist_summaries()
    emit("completed", stages_completed=len(stage_paths))
    return {"stages_completed": len(stage_paths), "outputs": sorted(p.name for p in output.iterdir()),
            "warnings": warnings, "timing": timing_doc(), "actual_backend": actual_backend}

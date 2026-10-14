"""Task execution and durable scientific outputs."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable

import numpy as np

from .config import source_config, validate_simulation_config, validate_targets
from .strict_ga import _apply_scientific_settings, run_strict_stage
from corrosion_model.ga_优化版 import GAConfig, run_ga
from corrosion_model.ca_优化版 import first_metal_depth


PARAMETER_NAMES = (
    "p_uniform_base", "p_passive_base", "p_break", "cl_threshold",
    "alpha_corrosion", "sensitive_point", "alpha_p_break", "p_h", "p_v", "p_o",
)
METRIC_NAMES = (
    "mean_depth_um", "nonuniform_depth_um", "mu_log_ratio",
    "mu_log_depth", "sigma_log_ratio", "sigma_log_depth",
)


def _atomic_npz(path: Path, **arrays) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _read_stage(path: Path):
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key].copy() for key in data.files}


def _plot_stage(path: Path, a: np.ndarray, space_xy: float, space_z: float, cmap: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for font_name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC"):
        if font_name in {item.name for item in font_manager.fontManager.ttflist}:
            plt.rcParams["font.sans-serif"] = [font_name]
            break

    depth = (first_metal_depth(a, a.shape[0], a.shape[1], a.shape[2]) - 1) * space_z
    fig, ax = plt.subplots(figsize=(7, 4.5))
    image = ax.imshow(depth.T, origin="lower", cmap=cmap, aspect="auto",
                      extent=(0, a.shape[0] * space_xy / 1000, 0, a.shape[1] * space_xy / 1000))
    ax.set(xlabel="X / mm", ylabel="Y / mm", title="首次金属层深度 / μm")
    fig.colorbar(image, ax=ax, label="μm")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def run_simulation(spec: dict, job_dir: Path, progress: Callable[[dict], None] | None = None) -> dict:
    config = validate_simulation_config(spec["config"])
    targets = spec["targets"]
    validate_targets(targets, spec["run_mode"])
    if config["mode"] == "fast" and config["TAICHI_CONFIG"]["use_taichi"]:
        try:
            import taichi  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("高速模式已选择 Taichi，但当前 Python 未安装 taichi") from exc
    _apply_scientific_settings(config)
    job_dir = Path(job_dir)
    output = job_dir / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    frozen = {"config": config, "targets": targets, "run_mode": spec["run_mode"]}
    fingerprint = hashlib.sha256(json.dumps(frozen, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()
    _atomic_json(job_dir / "request.json", frozen)
    arrays = []
    summaries = []
    started = time.perf_counter()
    geometry = config["GEOMETRY_CONFIG"]
    settings = config["STAGE_GA_CONFIG"]
    ga_settings = config["GA_CONFIG"]
    previous = None
    warnings = []
    for index, row in enumerate(targets, start=1):
        stage_file = output / f"stage_{index:03d}.npz"
        if stage_file.exists() and config["mode"] == "strict":
            result = _read_stage(stage_file)
        else:
            if config["mode"] == "strict":
                stage = run_strict_stage(
                    np.asarray(row, dtype=np.float64), config, index,
                    job_dir / "checkpoints" / f"stage_{index:03d}", fingerprint,
                    a_input=None if previous is None else previous["perfect_a"],
                    d_input=None if previous is None else previous["perfect_d"],
                    cl_input=None if previous is None else previous["perfect_cl"],
                    progress=progress,
                )
            else:
                options = GAConfig(
                    nind=int(settings["nind"]), selected_count=int(settings["selected_count"]),
                    maxgen=int(settings["maxgen"]), parallel_workers=int(settings["parallel_workers"]),
                    bits_per_param=int(ga_settings["bits_per_param"]),
                    base_px=float(ga_settings["base_px"]), base_pm=float(ga_settings["base_pm"]),
                    decay_rate=float(ga_settings["decay_rate"]), sigma_share=float(ga_settings["sigma_share"]),
                )
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
                )
            result = {
                "perfect_result": stage.perfect_result,
                "perfect_parameter": stage.perfect_parameter,
                "perfect_a": stage.perfect_a,
                "perfect_d": stage.perfect_d,
                "perfect_cl": stage.perfect_cl,
                "generations": np.asarray(stage.generations),
            }
            _atomic_npz(stage_file, **result)
        previous = result
        arrays.append(result)
        summary = {
            "stage": index, "target": row, "four_errors": result["perfect_result"].tolist(),
            "parameters": dict(zip(PARAMETER_NAMES, result["perfect_parameter"].tolist())),
            "generations": int(result["generations"]),
            "state_file": stage_file.name, "plot_file": f"stage_{index:03d}.png",
        }
        summaries.append(summary)
        if progress is not None:
            progress({"stage": index, "stages_completed": index, "total_stages": len(targets)})

    _atomic_npz(
        output / "simulation.npz",
        perfect_result_sd=np.stack([item["perfect_result"] for item in arrays]),
        perfect_parameter_sd=np.stack([item["perfect_parameter"] for item in arrays]),
        a_sd=np.stack([item["perfect_a"] for item in arrays]),
        d_sd=np.stack([item["perfect_d"] for item in arrays]),
        cl_sd=np.stack([item["perfect_cl"] for item in arrays]),
        perfect_a=arrays[-1]["perfect_a"], perfect_d=arrays[-1]["perfect_d"],
        perfect_cl=arrays[-1]["perfect_cl"],
        stage_numbers=np.arange(1, len(arrays) + 1),
    )
    with (output / "stage_metrics.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["stage", *METRIC_NAMES, "error_mean", "error_nonuniform", "error_mu_ratio", "error_depth_combined", *PARAMETER_NAMES])
        for row, summary in zip(targets, summaries):
            writer.writerow([summary["stage"], *row, *summary["four_errors"], *summary["parameters"].values()])
    for index, item in enumerate(arrays, start=1):
        try:
            _plot_stage(output / f"stage_{index:03d}.png", item["perfect_a"],
                        float(geometry["space_xy_um"]), float(geometry["space_z_um"]),
                        str(config["FIGURE_CONFIG"]["surface_cmap"]))
        except Exception as exc:
            warnings.append(f"阶段{index}绘图失败：{exc}")
    summary_doc = {
        "mode": config["mode"], "actual_backend": "Taichi" if config["TAICHI_CONFIG"]["use_taichi"] else "NumPy",
        "seed": int(ga_settings["seed"]), "stages": summaries,
        "simulation_seconds": round(time.perf_counter() - started, 3),
        "warnings": warnings,
        "objective_rule": "六指标误差去除第5项；深度均值/标准差按0.6/0.4合并；四项按0.1/0.3/0.2/0.4加权。",
    }
    _atomic_json(output / "summary.json", summary_doc)
    return {"stages_completed": len(arrays), "outputs": [p.name for p in output.iterdir()], "warnings": warnings}

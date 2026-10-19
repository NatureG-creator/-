"""独立测量矩阵、同种子配对和轻量持久化。"""
from __future__ import annotations

import copy
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from .benchmark import MODES, build_variants, compare_arrays
from .benchmark_archive import ensure_benchmark_bundle, report_csv
from .checkpoint import _replace_bytes, engine_environment_fingerprint
from .runner import _atomic_json
from .system_info import ROOT, runtime_provenance


def pack_report(output):
    return ensure_benchmark_bundle(Path(output).parent)


def cancel_report(job_dir, active_mode=None):
    output = Path(job_dir) / "outputs"
    path = output / "summary.json"
    if path.is_file():
        report = json.loads(path.read_text(encoding="utf-8"))
        report.update(cancelled=True, active_mode_at_stop=active_mode,
                      warning="用户停止测速；已完成方案保留，未完成方案不参与结论。下载ZIP时会按这份报告打包。")
        _atomic_json(path, report)
        _replace_bytes(output / "benchmark_results.csv", report_csv(report))


def terminate_tree(process):
    if process.poll() is not None:
        return
    import psutil
    try:
        parent = psutil.Process(process.pid)
        for child in parent.children(recursive=True)[::-1]:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        process.kill()
    except (psutil.NoSuchProcess, ProcessLookupError):
        pass
    process.wait(timeout=10)


def sample_rss(pid):
    try:
        import psutil
        parent = psutil.Process(pid)
        processes = [parent, *parent.children(recursive=True)]
        return sum(process.memory_info().rss for process in processes if process.is_running())
    except Exception:
        return None


def run_benchmark(spec: dict, job_dir: Path, progress=None) -> dict:
    job_dir = Path(job_dir)
    output = job_dir / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    _atomic_json(output / "benchmark_inputs.json", spec)
    variants = build_variants(spec)
    started = time.perf_counter()
    rows, paired = [], set()
    report = {"kind": "benchmark", "input_hash": spec["input_hash"], "options": spec["options"],
              "target": spec["target"], "rows": rows, "scope_note": spec["scope_note"],
              "stage_number": spec.get("stage_number", 1), "initial_state_info": spec.get("initial_state_info"),
              "provenance": runtime_provenance(), "engine_fingerprint": engine_environment_fingerprint(),
              "hardware": {"cpu": platform.processor(), "machine": platform.machine(),
                           "logical_cpu_count": os.cpu_count(), "platform": platform.platform()},
              "memory_note": "50ms采样方案父子进程RSS和，覆盖导入/计算/导出；可能重计共享页、漏瞬时峰值，不含GPU显存。",
              "parallel_note": "recreate计入每次建池；persistent首轮建池，重复样本复用worker。进程内线程数为配置预算，不是瞬时线程采样。",
              "objective_note": "population的objv为所有个体六项舍入误差；short_ga为原GA最终四项误差；a是分类状态，容差接近要求a完全一致。",
              "started_at": time.time(), "execution_order": [v["variant_id"] for v in variants],
              "comparison_seconds": 0.0, "report_export_seconds": 0.0,
              "archive_note": "ZIP按需生成并缓存；打包耗时写入bundle_info.json，独立于计算总耗时。"}

    def persist():
        tick = time.perf_counter()
        report["completed_modes"] = len(rows)
        report["total_modes"] = len(variants)
        report["successful_modes"] = sum(row["state"] == "completed" for row in rows)
        report["counts"] = {name: sum(row["state"] == name for row in rows)
                            for name in ("completed", "unavailable", "failed", "timeout")}
        report["wall_seconds"] = time.perf_counter() - started
        _replace_bytes(output / "benchmark_results.csv", report_csv(report))
        report["report_export_seconds"] += time.perf_counter() - tick
        _atomic_json(output / "summary.json", report)

    def pair_completed():
        by_id = {row["variant_id"]: row for row in rows}
        for row in rows:
            reference = by_id.get(row["baseline_id"])
            if row["state"] != "completed" or not reference or reference["state"] != "completed" or row["variant_id"] in paired:
                continue
            tick = time.perf_counter()
            left = output / "trials" / reference["variant_id"] / "arrays.npz"
            right = output / "trials" / row["variant_id"] / "arrays.npz"
            try:
                row["comparison"] = compare_arrays(left, right)
                row["speedup"] = reference["median_seconds"] / row["median_seconds"] if row["median_seconds"] > 0 else None
            except Exception as exc:
                row["comparison_warning"] = "数值文件对照未完成：" + str(exc)
                row.pop("speedup", None)
            else:
                try:
                    from .benchmark_analysis import physical_comparison
                    row["physical_comparison"] = physical_comparison(left, right, spec["config"],
                                                        output / "trials" / row["variant_id"] / "surface_difference.png")
                except Exception as exc:
                    row["physical_comparison_warning"] = "物理后处理或绘图未完成：" + str(exc)
            paired.add(row["variant_id"])
            report["comparison_seconds"] += time.perf_counter() - tick

    persist()
    for variant in variants:
        mode, identity = variant["mode"], variant["variant_id"]
        folder = output / "trials" / identity
        folder.mkdir(parents=True, exist_ok=True)
        if progress:
            progress({"phase": "benchmark", "benchmark_mode": identity, "label": MODES[mode],
                      "completed_modes": len(rows), "total_modes": len(variants)})
        trial_spec = copy.deepcopy(spec)
        trial_spec["options"].update({key: variant[key] for key in ("workers", "seed", "pool_policy")})
        if variant["pool_policy"] == "direct":
            trial_spec["options"]["pool_policy"] = "recreate"
        trial_spec["population"] = spec.get("populations", {}).get(str(variant["seed"]), spec["population"])
        trial_spec["config"]["GA_CONFIG"]["seed"] = variant["seed"]
        if spec.get("initial_state_path"):
            trial_spec["initial_state_path"] = str((job_dir / spec["initial_state_path"]).resolve())
        _atomic_json(folder / "trial_request.json", trial_spec)
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
            environment[key] = str(spec["options"].get("threads_per_worker", 1))
        tick, peak, timeout = time.perf_counter(), None, False
        row = {**variant, "label": MODES[mode], "stage_number": spec.get("stage_number", 1)}
        try:
            with (folder / "trial.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen([sys.executable, "-u", "-m", "backend.benchmark_trial",
                                str((folder / "trial_request.json").resolve()), mode, str(folder.resolve())],
                                cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                close_fds=True,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    while process.poll() is None:
                        memory = sample_rss(process.pid)
                        if memory is not None:
                            peak = max(peak or 0, memory)
                        if time.perf_counter() - tick > spec["options"]["timeout_seconds"]:
                            timeout = True
                            terminate_tree(process)
                            break
                        time.sleep(.05)
                finally:
                    if process.poll() is None:
                        terminate_tree(process)
            result_path = folder / "trial.json"
            if timeout:
                row.update(state="timeout", reason="达到单方案超时限制，已停止该方案及子进程")
            elif result_path.is_file():
                row.update(json.loads(result_path.read_text(encoding="utf-8")))
                row.update(variant)
            else:
                row.update(state="failed", reason=f"子进程退出码{process.returncode}，未生成结果，请下载trial.log")
        except Exception as exc:
            row.update(state="failed", reason="无法执行该方案：" + str(exc))
        row.update(process_wall_seconds=time.perf_counter() - tick, sampled_peak_rss_bytes=peak)
        rows.append(row)
        pair_completed()
        persist()
    if not spec["options"].get("retain_detail", True):
        from .benchmark_archive import benchmark_artifact_lock
        try:
            with benchmark_artifact_lock(job_dir):
                for row in rows:
                    folder = output / "trials" / row["variant_id"]
                    for name in ("first_arrays.npz", "arrays.npz"):
                        (folder / name).unlink(missing_ok=True)
            report["detail_note"] = "对照流程已结束；按设置移除原始大数组，仅保留输入、JSON、CSV、日志和图片。具体有效性以各方案状态和对照警告为准。"
        except (TimeoutError, OSError) as exc:
            report["detail_note"] = "可选明细清理未完成，已保留剩余文件和测量结果：" + str(exc)
    else:
        report["detail_note"] = "保留首轮与末轮原始数组，支持下载后复核数值与物理对照。"
    if not report["successful_modes"]:
        report["warning"] = "全部方案失败或不可用，未得出性能结论。"
    elif any(r["mode"] == "numpy_serial" and r["state"] != "completed" for r in rows):
        report["warning"] = "部分种子NumPy基准失败；对应组不生成加速比。"
    persist()
    if progress:
        progress({"completed_modes": len(rows), "total_modes": len(rows)})
    return report

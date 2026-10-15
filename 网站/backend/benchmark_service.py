"""Sequential isolated experiments, durable reports and process-tree telemetry."""
from __future__ import annotations

import csv
import io
import json
import os
import platform
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from .benchmark import MODES, SCOPE_NOTE, compare_arrays
from .checkpoint import engine_environment_fingerprint
from .runner import _atomic_json
from .system_info import ROOT, runtime_provenance


def pack_report(output):
    from .checkpoint import _atomic_replace
    temporary = output / "benchmark_bundle.zip.tmp"
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for path in sorted(output.rglob("*")):
                if path.is_file() and path.name != "benchmark_bundle.zip" and path.suffix != ".tmp":
                    archive.write(path, path.relative_to(output).as_posix())
        _atomic_replace(temporary, output / "benchmark_bundle.zip")
    finally:
        temporary.unlink(missing_ok=True)


def cancel_report(job_dir, active_mode=None):
    output = Path(job_dir) / "outputs"
    path = output / "summary.json"
    if path.is_file():
        report = json.loads(path.read_text(encoding="utf-8"))
        report["warning"] = "用户停止测速；仅已完成方案有有效计时，当前未完成方案不参与结论。"
        report["cancelled"] = True
        report["active_mode_at_stop"] = active_mode
        _atomic_json(path, report)
        pack_report(output)


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
        total = 0
        for process in processes:
            try:
                total += process.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return total
    except Exception:
        return None


def run_benchmark(spec: dict, job_dir: Path, progress=None) -> dict:
    job_dir = Path(job_dir)
    output = job_dir / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    spec_path = output / "benchmark_inputs.json"
    _atomic_json(spec_path, spec)
    started = time.perf_counter()
    rows = []
    report = {"kind": "benchmark", "input_hash": spec["input_hash"],
              "options": spec["options"], "target": spec["target"], "rows": rows,
              "scope_note": SCOPE_NOTE, "provenance": runtime_provenance(),
              "engine_fingerprint": engine_environment_fingerprint(),
              "memory_note": "50ms采样方案父子进程RSS之和；共享页可能重复计数、瞬时峰值可能遗漏，不含GPU显存。",
              "parallel_note": "多进程方案每次评估重新建立进程池；计入创建、编译和传输，不宣称常驻池纯内核性能。",
              "objective_note": "objv是原CA六项舍入误差；a/d/cl为所有个体完整状态。严格相等与容差接近分别报告。",
              "started_at": time.time()}
    report["hardware"] = {"cpu": platform.processor(), "machine": platform.machine(),
                          "logical_cpu_count": os.cpu_count(), "platform": platform.platform()}
    report["trial_thread_environment"] = {key: "1" for key in
                                            ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")}

    def persist():
        report["wall_seconds"] = time.perf_counter() - started
        _atomic_json(output / "summary.json", report)
        fields = ["mode", "label", "state", "actual_arch", "workers", "initialization_seconds",
                  "first_seconds", "median_seconds", "min_seconds", "max_seconds", "speedup",
                  "repeat_exact", "process_wall_seconds", "sampled_peak_rss_bytes", "reason"]
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields + ["exact", "within_tolerance", "samples_seconds"])
        writer.writeheader()
        for row in rows:
            item = {key: row.get(key) for key in fields}
            item.update({key: row.get("comparison", {}).get(key) for key in ("exact", "within_tolerance")})
            item["samples_seconds"] = json.dumps(row.get("samples_seconds", []))
            writer.writerow(item)
        from .checkpoint import _replace_bytes
        _replace_bytes(output / "benchmark_results.csv", buffer.getvalue().encode("utf-8-sig"))
        pack_report(output)

    persist()
    for mode in spec["options"]["modes"]:
        folder = output / "trials" / mode
        folder.mkdir(parents=True, exist_ok=True)
        if progress:
            progress({"phase": "benchmark", "benchmark_mode": mode, "label": MODES[mode],
                      "completed_modes": len(rows), "total_modes": len(spec["options"]["modes"])})
        tick = time.perf_counter()
        peak = None
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        # Freeze explicit numerical thread settings for all compared modes.
        for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
            environment[key] = "1"
        with (folder / "trial.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, "-u", "-m", "backend.benchmark_trial",
                                        str(spec_path.resolve()), mode, str(folder.resolve())],
                                       cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            timeout = False
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
        result_file = folder / "trial.json"
        if timeout:
            row = {"mode": mode, "label": MODES[mode], "state": "timeout", "reason": "达到单方案超时限制，已停止该方案及其子进程"}
        elif result_file.is_file():
            row = json.loads(result_file.read_text(encoding="utf-8"))
        else:
            row = {"mode": mode, "label": MODES[mode], "state": "failed",
                   "reason": f"子进程退出码{process.returncode}，未生成结果，请下载trial.log"}
        row.update(process_wall_seconds=time.perf_counter() - tick, sampled_peak_rss_bytes=peak)
        if row["state"] == "completed":
            baseline = output / "trials" / "numpy_serial" / "arrays.npz"
            if baseline.is_file() and (mode == "numpy_serial" or rows and rows[0]["state"] == "completed"):
                row["comparison"] = compare_arrays(baseline, folder / "arrays.npz")
                base_seconds = row["median_seconds"] if mode == "numpy_serial" else rows[0]["median_seconds"]
                row["speedup"] = base_seconds / row["median_seconds"] if row["median_seconds"] > 0 else None
        rows.append(row)
        persist()
    report["completed_modes"] = len(rows)
    report["successful_modes"] = sum(row["state"] == "completed" for row in rows)
    if not report["successful_modes"]:
        report["warning"] = "全部方案失败或不可用，未得出性能结论。"
    elif rows[0]["state"] != "completed":
        report["warning"] = "NumPy基准失败，其他耗时仅供诊断，不生成加速比。"
    persist()
    if progress:
        progress({"completed_modes": len(rows), "total_modes": len(rows)})
    return report

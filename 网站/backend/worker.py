"""Separate process for long-running simulation and MATLAB jobs."""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

from .pointcloud_runner import run_pointcloud
from .finite_element_export import create_surface_bundle
from .runner import _atomic_json, run_simulation
from .system_info import process_alive


def run_job(job_id: str, runtime: Path) -> None:
    job_dir = runtime / "jobs" / job_id
    spec = json.loads((job_dir / "spec.json").read_text(encoding="utf-8"))
    status_path = job_dir / "status.json"

    def update(changes: dict):
        state = json.loads(status_path.read_text(encoding="utf-8"))
        state.update(changes)
        state["updated_at"] = time.time()
        _atomic_json(status_path, state)

    lock_path = job_dir / "worker.lock"
    if lock_path.exists():
        try:
            previous_pid = int(lock_path.read_text(encoding="ascii"))
        except (OSError, ValueError):
            previous_pid = None
        if process_alive(previous_pid):
            raise RuntimeError("该任务已经有活动进程，拒绝重复计算")
        lock_path.unlink(missing_ok=True)
    with lock_path.open("x", encoding="ascii") as lock:
        lock.write(str(os.getpid()))
    update({"state": "running", "phase": "starting", "pid": os.getpid(),
            "started_at": time.time(), "error": None})
    started = time.perf_counter()
    try:
        import psutil
        update({"process_created_at": psutil.Process().create_time()})
    except (ImportError, OSError):
        pass
    try:
        if spec["kind"] == "simulation":
            result = run_simulation(spec, job_dir, progress=update)
        elif spec["kind"] == "apdl_tension":
            from .apdl_service import run_apdl_job
            result=run_apdl_job(spec,job_dir,progress=update)
        elif spec["kind"] == "benchmark":
            from .benchmark_service import run_benchmark
            result = run_benchmark(spec, job_dir, progress=update)
        elif spec["kind"] == "diagnostics":
            from .benchmark_diagnostics import run_diagnostics
            update({"phase": "diagnostics"})
            result = run_diagnostics(job_dir / "outputs", spec.get("timeout_seconds", 30))
            _atomic_json(job_dir / "outputs" / "summary.json", result)
        elif spec["kind"] == "pointcloud":
            reference = job_dir / "inputs" / ("reference" + spec["reference_extension"])
            detail = job_dir / "inputs" / ("detail" + spec["detail_extension"])
            if not reference.exists():
                reference = (runtime / "uploads" / spec["reference_id"] / "input").with_suffix(spec["reference_extension"])
            if not detail.exists():
                detail = (runtime / "uploads" / spec["detail_id"] / "input").with_suffix(spec["detail_extension"])
            update({"phase": "matlab"})
            result = run_pointcloud(job_dir, reference, detail, spec["pointcloud_config"])
        else:
            update({"phase": "finite_element_export"})
            source = job_dir / spec["frozen_source_path"]
            result = create_surface_bundle(spec["source_kind"], source,
                                           job_dir / "outputs", spec["options"])
        update({"state": "completed", "phase": "completed", "result": result,
                "elapsed_seconds": round(time.perf_counter() - started, 3)})
    except Exception as exc:
        traceback.print_exc()
        update({"state": "failed", "error": str(exc),
                "elapsed_seconds": round(time.perf_counter() - started, 3)})
    finally:
        lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    run_job(sys.argv[1], Path(os.environ["CORROSION_RUNTIME_DIR"]))

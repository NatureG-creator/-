"""Separate process for long-running simulation and MATLAB jobs."""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

from .pointcloud_runner import run_pointcloud
from .runner import _atomic_json, run_simulation


def run_job(job_id: str, runtime: Path) -> None:
    job_dir = runtime / "jobs" / job_id
    spec = json.loads((job_dir / "spec.json").read_text(encoding="utf-8"))
    status_path = job_dir / "status.json"

    def update(changes: dict):
        state = json.loads(status_path.read_text(encoding="utf-8"))
        state.update(changes)
        state["updated_at"] = time.time()
        _atomic_json(status_path, state)

    update({"state": "running", "pid": os.getpid()})
    started = time.perf_counter()
    try:
        if spec["kind"] == "simulation":
            result = run_simulation(spec, job_dir, progress=update)
        else:
            reference = runtime / "uploads" / spec["reference_id"] / "input"
            detail = runtime / "uploads" / spec["detail_id"] / "input"
            reference = reference.with_suffix(spec["reference_extension"])
            detail = detail.with_suffix(spec["detail_extension"])
            result = run_pointcloud(job_dir, reference, detail, spec["pointcloud_config"])
        update({"state": "completed", "result": result,
                "elapsed_seconds": round(time.perf_counter() - started, 3)})
    except Exception as exc:
        traceback.print_exc()
        update({"state": "failed", "error": str(exc),
                "elapsed_seconds": round(time.perf_counter() - started, 3)})


if __name__ == "__main__":
    run_job(sys.argv[1], Path(os.environ["CORROSION_RUNTIME_DIR"]))

"""多工况调度：先校验全部输入，顺序组完成后再运行并行组。"""

from __future__ import annotations

import copy
import io
import json
import shutil
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor

from .config import validate_simulation_config, validate_targets
from .runner import _atomic_json
from .targets import load_targets
from .system_info import sha256


def _batch_status_path(server, batch_id):
    server.validate_id(batch_id)
    path = server.runtime / "batches" / batch_id / "status.json"
    if not path.is_file():
        raise FileNotFoundError("批次不存在")
    return path


def write_batch_archive(server, batch_id: str, stream) -> None:
    """Stream a portable ZIP of batch status and outputs to a seekable file."""
    status_path = _batch_status_path(server, batch_id)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"batch-{batch_id}/status.json",
                         json.dumps(status, ensure_ascii=False, indent=2))
        for job_id in status.get("job_ids", []):
            server.validate_id(job_id)
            job_root = server.runtime / "jobs" / job_id
            if not job_root.is_dir():
                continue
            for relative in ("status.json", "spec.json", "worker.log"):
                path = job_root / relative
                if path.is_file():
                    archive.write(path, f"batch-{batch_id}/jobs/{job_id}/{relative}")
            outputs = job_root / "outputs"
            if outputs.is_dir():
                for path in sorted(outputs.rglob("*")):
                    if path.is_file() and path.suffix != ".tmp":
                        relative = path.relative_to(job_root).as_posix()
                        archive.write(path, f"batch-{batch_id}/jobs/{job_id}/{relative}")


def batch_archive_bytes(server, batch_id: str) -> bytes:
    """Convenience helper for small archives and tests."""
    buffer = io.BytesIO()
    write_batch_archive(server, batch_id, buffer)
    return buffer.getvalue()


def stop_batch(server, batch_id: str) -> dict:
    """Stop all queued/running jobs in a batch and persist an auditable status."""
    status_path = _batch_status_path(server, batch_id)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    stopped, skipped = [], []
    status["state"] = "stopping"
    _atomic_json(status_path, status)
    for job_id in status.get("job_ids", []):
        try:
            state = server.get_job(job_id)
            if state.get("state") in {"queued", "running", "pending", "created", "stopping"}:
                server.stop(job_id)
                stopped.append(job_id)
            else:
                skipped.append({"id": job_id, "state": state.get("state")})
        except (ValueError, FileNotFoundError) as exc:
            skipped.append({"id": job_id, "error": str(exc)})
    remaining = [job_id for job_id in status.get("job_ids", []) if
                 server.get_job(job_id)["state"] in {"queued", "running"}]
    status.update({"state": "needs_attention" if remaining else "stopped",
                   "active_job_ids": remaining, "stopped_at": time.time(),
                   "stopped_job_ids": stopped, "skipped_jobs": skipped,
                   "updated_at": time.time()})
    _atomic_json(status_path, status)
    return status


def retry_failed_batch(server, batch_id: str) -> dict:
    """Resume only failed/interrupted strict jobs with a verified checkpoint."""
    status_path = _batch_status_path(server, batch_id)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    retried, skipped = [], []
    for job_id in status.get("job_ids", []):
        state = server.get_job(job_id)
        if state["state"] not in {"failed", "interrupted"}:
            skipped.append({"id": job_id, "state": state["state"]})
            continue
        try:
            server.resume(job_id)
            retried.append(job_id)
        except (ValueError, FileNotFoundError) as exc:
            skipped.append({"id": job_id, "error": str(exc)})
    if retried:
        status.update(state="running", retried_job_ids=retried, updated_at=time.time())
        _atomic_json(status_path, status)
        def watch_retries():
            while True:
                states = [server.get_job(job_id)["state"] for job_id in status["job_ids"]]
                if not any(state in {"queued", "running"} for state in states):
                    latest = json.loads(status_path.read_text(encoding="utf-8"))
                    if latest.get("state") not in {"stopping", "stopped"}:
                        latest.update(state="completed" if all(state == "completed" for state in states)
                                      else "needs_attention", updated_at=time.time(),
                                      completed_count=sum(state == "completed" for state in states),
                                      failed_count=sum(state in {"failed", "interrupted"} for state in states))
                        _atomic_json(status_path, latest)
                    return
                time.sleep(.2)
        threading.Thread(target=watch_retries, daemon=True,
                         name=f"batch-retry-{batch_id}").start()
    return {"id": batch_id, "state": status["state"],
            "retried_job_ids": retried, "skipped_jobs": skipped}


def create_batch(server, payload):
    config = validate_simulation_config(copy.deepcopy(payload["config"]))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 50:
        raise ValueError("工况清单必须包含1到50个工况")
    mode = payload.get("run_mode", "sequential")
    if mode not in {"single", "sequential", "parallel", "mixed"}:
        raise ValueError("工况模式必须为single/sequential/parallel/mixed")
    workers = payload.get("parallel_case_workers", 2)
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 8:
        raise ValueError("并行工况数必须为1到8；全站最多同时启动2个计算任务")
    if mode == "single" and len(cases) != 1:
        raise ValueError("单工况模式只能提交一个工况")
    prepared, names = [], set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("工况必须为对象")
        name = case.get("case_name", "")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("工况名称必须非空且不重复")
        names.add(name)
        case_mode = case.get("mode", "parallel" if mode == "parallel" else "sequential")
        if mode == "mixed":
            if case_mode not in {"sequential", "parallel"}:
                raise ValueError("mixed工况必须标记sequential或parallel")
            if not payload.get(case_mode + "_enabled", False):
                raise ValueError(f"{case_mode}分组已关闭，但清单仍包含该组工况，请修改清单")
        if case.get("upload_id"):
            record, path = server.get_upload(case["upload_id"])
            if sha256(path) != record["sha256"]:
                raise ValueError("上传目标文件已被修改，请重新上传")
            targets = load_targets(path, case.get("variable"), case.get("orientation", "auto"))
        else:
            targets = case.get("targets")
        simulation_mode = case.get("simulation_mode", "staged")
        validate_targets(targets, simulation_mode)
        prepared.append(({**case, **({"engine_release": payload["engine_release"]} if "engine_release" in payload else {}), "kind": "simulation", "config": config,
                          "run_mode": simulation_mode, "targets": targets}, case_mode))
    # 只有所有工况通过校验后才创建任务目录和启动线程。
    jobs = []
    try:
        for item, group in prepared:
            jobs.append((server.create_job(item, launch=False), group))
    except Exception:
        # 准备期尚未启动计算，仅回滚本批次已创建的任务。
        for job, _ in jobs:
            server.pending_jobs.discard(job["id"])
            shutil.rmtree(server.runtime / "jobs" / job["id"])
        raise
    batch_id = uuid.uuid4().hex[:16]
    folder = server.runtime / "batches" / batch_id
    folder.mkdir()
    status = {"id": batch_id, "state": "queued", "run_mode": mode, "created_at": time.time(),
              "job_ids": [job["id"] for job, _ in jobs], "actual_parallel_limit": min(2, workers)}
    _atomic_json(folder / "status.json", status)

    def run_one(job):
        if json.loads((folder / "status.json").read_text(encoding="utf-8")).get("state") in {"stopping", "stopped"}:
            return
        current = server.get_job(job["id"])
        if current["state"] != "queued":
            return
        server.launch(job["id"])
        while server.get_job(job["id"])["state"] in {"queued", "running"}:
            time.sleep(.1)

    def run_batch():
        if json.loads((folder / "status.json").read_text(encoding="utf-8")).get("state") in {"stopping", "stopped"}:
            return
        status["state"] = "running"
        _atomic_json(folder / "status.json", status)
        try:
            if mode in {"single", "sequential"}:
                for job, _ in jobs:
                    run_one(job)
            else:
                if mode == "mixed":
                    for job, group in jobs:
                        if group == "sequential":
                            run_one(job)
                parallel = [job for job, group in jobs if mode == "parallel" or group == "parallel"]
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    list(executor.map(run_one, parallel))
            states = [server.get_job(job["id"])["state"] for job, _ in jobs]
            status["state"] = "completed" if all(state == "completed" for state in states) else "needs_attention"
        except Exception as exc:
            status.update(state="failed", error=str(exc))
        final = json.loads((folder / "status.json").read_text(encoding="utf-8"))
        if final.get("state") in {"stopping", "stopped"}:
            status["state"] = "stopped"
        status["completed_count"] = sum(state == "completed" for state in states) if 'states' in locals() else 0
        status["failed_count"] = sum(state in {"failed", "interrupted"} for state in states) if 'states' in locals() else 0
        status["updated_at"] = time.time()
        _atomic_json(folder / "status.json", status)

    threading.Thread(target=run_batch, daemon=True, name=f"batch-{batch_id}").start()
    return {**status, "jobs": [job for job, _ in jobs]}

"""多工况调度：先校验全部输入，顺序组完成后再运行并行组。"""

from __future__ import annotations

import copy
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from .config import validate_simulation_config, validate_targets
from .runner import _atomic_json
from .targets import load_targets
from .system_info import sha256


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
        prepared.append(({**case, "kind": "simulation", "config": config,
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
        current = server.get_job(job["id"])
        if current["state"] != "queued":
            return
        server.launch(job["id"])
        while server.get_job(job["id"])["state"] in {"queued", "running"}:
            time.sleep(.1)

    def run_batch():
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
        status["updated_at"] = time.time()
        _atomic_json(folder / "status.json", status)

    threading.Thread(target=run_batch, daemon=True, name=f"batch-{batch_id}").start()
    return {**status, "jobs": [job for job, _ in jobs]}

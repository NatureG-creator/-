"""任务目录、输入冻结和本机进程管理。"""

from __future__ import annotations

import copy
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from contextlib import ExitStack, nullcontext
from pathlib import Path

from .config import validate_simulation_config, validate_targets
from .pointcloud_config import validate_pointcloud_config
from .pointcloud_runner import POINT_EXTENSIONS, inspect_xyz
from .runner import _atomic_json
from .system_info import ROOT, find_matlab, json_record, process_alive, sha256
from .targets import inspect_target, load_targets

UPLOAD_EXTENSIONS = POINT_EXTENSIONS | {".mat", ".xlsx"}
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024


class JobService:
    def initialize(self, runtime: Path):
        self.runtime = Path(runtime)
        for folder in ("jobs", "uploads", "batches"):
            (self.runtime / folder).mkdir(parents=True, exist_ok=True)
        self.processes: dict[str, subprocess.Popen] = {}
        self._job_lock = threading.RLock()
        self.compute_slots = threading.BoundedSemaphore(2)
        self.benchmark_gate = threading.Lock()
        self.pending_jobs = set()
        self._launching_jobs = {}
        # 服务退出不等于独立计算进程退出；接管现存任务的并发占用。
        inherited = {}
        inherited_weights = {}
        for folder in (self.runtime / "jobs").iterdir():
            status = json_record(folder / "status.json", {})
            try:
                locked_pid = int((folder / "worker.lock").read_text(encoding="ascii"))
            except (OSError, ValueError):
                continue
            if (status.get("state") in {"queued", "running"} and
                    status.get("pid") in {None, locked_pid} and process_alive(locked_pid)):
                inherited[folder.name] = locked_pid
                inherited_weights[folder.name] = 2 if status.get("kind") == "benchmark" else 1
        self.inherited_processes = inherited
        reserved = min(2, sum(inherited_weights.values()))
        for _ in range(reserved):
            self.compute_slots.acquire(blocking=False)
        if inherited:
            def watch_inherited():
                remaining_reserved = reserved
                while inherited:
                    for job_id, pid in list(inherited.items()):
                        if not process_alive(pid):
                            inherited.pop(job_id, None)
                    required = min(2, sum(inherited_weights[job_id] for job_id in inherited))
                    while remaining_reserved > required:
                        self.compute_slots.release()
                        remaining_reserved -= 1
                    if inherited:
                        time.sleep(.1)
            threading.Thread(target=watch_inherited, daemon=True,
                             name="inherited-workers").start()

    @staticmethod
    def validate_id(value, length=16):
        if not isinstance(value, str) or len(value) != length or any(
                char not in "0123456789abcdef" for char in value):
            raise FileNotFoundError("编号无效")
        return value

    def upload(self, name, stream, length):
        extension = Path(name).suffix.lower()
        if extension not in UPLOAD_EXTENSIONS:
            raise ValueError("文件类型仅支持 TXT、CSV、TSV、XYZ、MAT、XLSX")
        if not isinstance(length, int) or not 0 < length <= MAX_UPLOAD_BYTES:
            raise ValueError("文件必须非空且不超过1GB")
        upload_id = uuid.uuid4().hex
        folder = self.runtime / "uploads" / upload_id
        folder.mkdir()
        try:
            destination = folder / f"input{extension}"
            with destination.open("wb") as output:
                remaining = length
                while remaining:
                    block = stream.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ValueError("上传数据不完整")
                    output.write(block)
                    remaining -= len(block)
            record = {"id": upload_id, "name": Path(name.replace("\\", "/")).name[:255],
                      "extension": extension, "bytes": length, "uploaded_at": time.time(),
                      "sha256": sha256(destination)}
            _atomic_json(folder / "metadata.json", record)
            return record
        except Exception:
            shutil.rmtree(folder)
            raise

    def get_upload(self, upload_id):
        self.validate_id(upload_id, 32)
        folder = self.runtime / "uploads" / upload_id
        record = json_record(folder / "metadata.json")
        if record is None:
            raise FileNotFoundError("上传文件不存在")
        return record, folder / f"input{record['extension']}"

    def create_job(self, payload: dict, *, launch=True):
        if not isinstance(payload, dict):
            raise ValueError("任务请求必须是对象")
        kind = payload.get("kind")
        if kind not in {"simulation", "pointcloud", "finite_element", "benchmark"}:
            raise ValueError("任务类型必须为 simulation、pointcloud、finite_element 或 benchmark")
        job_id = uuid.uuid4().hex[:16]
        job_dir = self.runtime / "jobs" / job_id
        started = time.perf_counter()
        if kind == "benchmark":
            from .benchmark import prepare_benchmark
            spec = prepare_benchmark(payload)
        elif kind == "simulation":
            config = validate_simulation_config(copy.deepcopy(payload["config"]))
            run_mode = payload.get("run_mode", "staged")
            source_info = None
            if payload.get("upload_id"):
                source_info, source = self.get_upload(payload["upload_id"])
                targets = load_targets(source, payload.get("variable"),
                                       payload.get("orientation", "auto"))
                if sha256(source) != source_info["sha256"]:
                    raise ValueError("上传目标文件已被修改，请重新上传")
            else:
                targets = payload.get("targets")
            validate_targets(targets, run_mode)
            config["ACTIVE_STAGE_TARGET_DATA"] = targets
            config["TARGET_SOURCE"] = "matlab" if source_info and source_info["extension"] == ".mat" else "manual"
            if run_mode == "single":
                config["SINGLE_STAGE_TARGET_DATA"] = targets[0]
            if payload.get("random_seed"):
                config["GA_CONFIG"]["seed"] = int.from_bytes(os.urandom(4), "big")
            validate_simulation_config(config)
            if config["mode"] == "fast" and not config["TAICHI_CONFIG"]["use_taichi"]:
                raise ValueError("高速模式要求启用Taichi；如需NumPy请选择严格模式")
            if config["TAICHI_CONFIG"]["use_taichi"]:
                import importlib.util
                if importlib.util.find_spec("taichi") is None:
                    raise ValueError("当前Python未安装Taichi，请使用严格模式或安装可兼容版本")
            from .parameter_catalog import estimate_resources
            spec = {"kind": kind, "config": config, "targets": targets, "run_mode": run_mode,
                    "reading_seconds": time.perf_counter() - started,
                    "target_options": {"variable": payload.get("variable"),
                                       "orientation": payload.get("orientation", "auto")},
                    "target_source": source_info,
                    "resource_estimate": estimate_resources(config, len(targets), run_mode),
                    "case_name": str(payload.get("case_name", ""))[:100]}
        elif kind == "pointcloud":
            reference, ref_path = self.get_upload(payload["reference_id"])
            detail, detail_path = self.get_upload(payload["detail_id"])
            if reference["extension"] not in POINT_EXTENSIONS or detail["extension"] not in POINT_EXTENSIONS:
                raise ValueError("点云任务必须上传文本XYZ文件")
            if not find_matlab():
                raise ValueError("未检测到MATLAB；请先设置MATLAB_BIN或将matlab加入PATH")
            spec = {"kind": kind, "reference_id": reference["id"], "detail_id": detail["id"],
                    "reference_extension": reference["extension"],
                    "detail_extension": detail["extension"],
                    "pointcloud_config": validate_pointcloud_config(payload.get("pointcloud_config", {})),
                    "reference_preview": inspect_xyz(ref_path), "detail_preview": inspect_xyz(detail_path),
                    "input_hashes": {"reference": sha256(ref_path), "detail": sha256(detail_path)}}
        else:
            source_job_id = self.validate_id(payload.get("source_job_id"))
            source_state = self.get_job(source_job_id)
            if source_state.get("state") != "completed":
                raise ValueError("有限元导出的源任务必须已完成")
            source_kind = payload.get("source_kind")
            if source_kind not in {"simulation", "measured"}:
                raise ValueError("source_kind 必须是 simulation 或 measured")
            source_root = self.runtime / "jobs" / source_job_id / "outputs"
            if source_kind == "simulation":
                if source_state.get("kind") != "simulation":
                    raise ValueError("simulation 来源必须选择已完成的模拟任务")
                source_path = source_root / "simulation.npz"
                if not source_path.is_file():
                    raise ValueError("模拟任务缺少 simulation.npz，不能导出有限元表面")
            else:
                if source_state.get("kind") not in {"pointcloud", "finite_element"}:
                    raise ValueError("measured 来源必须选择点云或已有有限元导出任务")
                requested = str(payload.get("source_file", ""))
                candidates = [source_root / requested] if requested else []
                candidates.extend(path for path in sorted(source_root.rglob("*.mat")) if path not in candidates)
                source_path = None
                from .finite_element_export import _read_measured
                for candidate in candidates:
                    if candidate.is_file():
                        try:
                            _read_measured(candidate, payload.get("input_variable"))
                            source_path = candidate
                            break
                        except (KeyError, ValueError, OSError):
                            continue
                if source_path is None:
                    raise ValueError("点云任务结果中没有可用的 Z_filled/F_filled 表面 MAT")
            options = dict(payload.get("options") or {})
            try:
                options["space_z_um"] = float(options.get("space_z_um", 25.0))
                options["grid_spacing_mm"] = float(options.get("grid_spacing_mm", 0.05))
                options["origin_x_mm"] = float(options.get("origin_x_mm", 0.0))
                options["origin_y_mm"] = float(options.get("origin_y_mm", 0.0))
            except (TypeError, ValueError) as exc:
                raise ValueError("有限元导出尺寸参数必须是数值") from exc
            if options["space_z_um"] <= 0 or options["grid_spacing_mm"] <= 0:
                raise ValueError("space_z_um 和 grid_spacing_mm 必须大于0")
            if options.get("output_variable") not in {None, "", "Z_filled", "F_filled"}:
                raise ValueError("output_variable 只能是 Z_filled 或 F_filled")
            spec = {"kind": kind, "source_job_id": source_job_id, "source_kind": source_kind,
                    "source_path": str(source_path), "source_hash": sha256(source_path),
                    "source_file": source_path.name, "input_variable": payload.get("input_variable"),
                    "options": options, "reading_seconds": time.perf_counter() - started}
        job_dir.mkdir()
        try:
            (job_dir / "inputs").mkdir()
            if kind == "simulation" and source_info:
                shutil.copy2(source, job_dir / "inputs" / f"target{source.suffix}")
                spec["frozen_target_path"] = f"inputs/target{source.suffix}"
                if sha256(job_dir / spec["frozen_target_path"]) != source_info["sha256"]:
                    raise ValueError("冻结目标副本与上传文件不一致，请重新上传")
            if kind == "pointcloud":
                for label, source in (("reference", ref_path), ("detail", detail_path)):
                    shutil.copy2(source, job_dir / "inputs" / f"{label}{source.suffix}")
            if kind == "finite_element":
                frozen = job_dir / "inputs" / f"source{Path(spec['source_path']).suffix}"
                shutil.copy2(spec["source_path"], frozen)
                spec["frozen_source_path"] = f"inputs/{frozen.name}"
                if sha256(frozen) != spec["source_hash"]:
                    raise ValueError("有限元导出源文件冻结失败")
            _atomic_json(job_dir / "spec.json", spec)
            status = {"id": job_id, "kind": kind, "state": "queued", "created_at": time.time(),
                      "updated_at": time.time(), "pid": None, "phase": "queued",
                      "case_name": spec.get("case_name", "")}
            _atomic_json(job_dir / "status.json", status)
        except Exception:
            shutil.rmtree(job_dir)
            raise
        self.pending_jobs.add(job_id)
        if launch:
            self.launch(job_id)
        return status

    def launch(self, job_id):
        self.validate_id(job_id)
        with self._job_lock:
            current = json_record(self.runtime / "jobs" / job_id / "status.json", {})
            previous = self.processes.get(job_id)
            if process_alive(current.get("pid")) or (
                    job_id in self._launching_jobs and
                    (previous is None or previous.poll() is None)):
                raise ValueError("原任务进程仍在运行或排队，不能重复启动")
            token = uuid.uuid4().hex
            self._launching_jobs[job_id] = token
            self.processes.pop(job_id, None)
            self.pending_jobs.add(job_id)

        def scheduled():
            try:
                benchmark = current.get("kind") == "benchmark"
                # Benchmarks reserve both server slots; two concurrent benchmarks
                # must not each hold one slot and wait forever for the other.
                with self.benchmark_gate if benchmark else nullcontext():
                    with ExitStack() as slots:
                        for _ in range(2 if benchmark else 1):
                            slots.enter_context(self.compute_slots)
                        with self._job_lock:
                            if self._launching_jobs.get(job_id) != token:
                                return
                            process = self._start_process(job_id)
                        if process is not None:
                            process.wait()
            except Exception as exc:
                with self._job_lock:
                    if self._launching_jobs.get(job_id) == token:
                        failed_state = json_record(self.runtime / "jobs" / job_id / "status.json", {})
                        failed_state.update(state="failed", error=str(exc), updated_at=time.time())
                        _atomic_json(self.runtime / "jobs" / job_id / "status.json", failed_state)
            finally:
                with self._job_lock:
                    if self._launching_jobs.get(job_id) == token:
                        self._launching_jobs.pop(job_id, None)
                        self.pending_jobs.discard(job_id)

        threading.Thread(target=scheduled, daemon=True, name=f"job-{job_id}").start()

    def _start_process(self, job_id):
        with self._job_lock:
            current = json_record(self.runtime / "jobs" / job_id / "status.json", {})
            if current.get("state") != "queued":
                return None
            if process_alive(current.get("pid")) or job_id in self.processes and self.processes[job_id].poll() is None:
                raise ValueError("原任务进程仍在运行，不能重复启动")
            environment = os.environ.copy()
            environment["CORROSION_RUNTIME_DIR"] = str(self.runtime.resolve())
            environment["PYTHONIOENCODING"] = "utf-8"
            matlab = find_matlab()
            if matlab:
                environment["MATLAB_BIN"] = matlab
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            with (self.runtime / "jobs" / job_id / "worker.log").open("a", encoding="utf-8") as log:
                process = subprocess.Popen([sys.executable, "-u", "-m", "backend.worker", job_id],
                    cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=flags, start_new_session=os.name != "nt")
            self.processes[job_id] = process
            return process

    def get_job(self, job_id):
        self.validate_id(job_id)
        folder = self.runtime / "jobs" / job_id
        with self._job_lock:
            state = json_record(folder / "status.json")
            if state is None:
                raise FileNotFoundError("任务不存在")
            process = self.processes.get(job_id)
            if state["state"] in {"queued", "running"}:
                dead_owned = (process is not None and process.poll() is not None and
                              not (state["state"] == "queued" and job_id in self.pending_jobs))
                dead_orphan = process is None and (
                    state["state"] == "running" and not process_alive(state.get("pid")) or
                    state["state"] == "queued" and job_id not in self.pending_jobs)
                if dead_owned or dead_orphan:
                    state.update(state="interrupted", error="任务进程已退出，可检查保存的进度后恢复",
                                 updated_at=time.time())
                    _atomic_json(folder / "status.json", state)
            state["files"] = self.job_files(job_id)
            state["spec"] = json_record(folder / "spec.json", {})
            state["summary"] = json_record(folder / "outputs" / "summary.json")
            state["effective_config"] = json_record(folder / "outputs" / "effective_config.json")
            state["timing"] = json_record(folder / "outputs" / "timing.json")
            state["checkpoint"] = {
                "exists": any((folder / "checkpoints").rglob("progress.json")) if
                          (folder / "checkpoints").is_dir() else False,
                "available": state.get("kind") == "simulation" and
                             state["spec"].get("config", {}).get("mode") == "strict" and
                             state["state"] in {"failed", "interrupted"},
                "validated": False}
            state["progress"] = {key: state.get(key) for key in (
                "stage", "generation", "completed_individuals", "total_individuals", "phase",
                "stages_completed", "total_stages", "benchmark_mode", "label",
                "completed_modes", "total_modes")}
            if state["state"] == "running":
                state["elapsed_seconds"] = round(time.time() - state.get("started_at", state["created_at"]), 2)
            return state

    def job_files(self, job_id):
        self.validate_id(job_id)
        root = self.runtime / "jobs" / job_id / "outputs"
        if not root.is_dir():
            return []
        return [{"name": path.relative_to(root).as_posix(), "bytes": path.stat().st_size}
                for path in sorted(root.rglob("*")) if path.is_file() and
                path.resolve().is_relative_to(root.resolve()) and path.suffix != ".tmp"]

    def resume(self, job_id):
        with self._job_lock:
            state = self.get_job(job_id)
            spec = state["spec"]
            if spec.get("kind") != "simulation" or spec["config"]["mode"] != "strict":
                raise ValueError("只有严格可复现模拟支持恢复")
            if state["state"] not in {"failed", "interrupted"} or process_alive(state.get("pid")):
                raise ValueError("任务当前不能恢复，原任务可能仍在运行")
            from .runner import precheck_resume
            if spec.get("frozen_target_path"):
                target = self.runtime / "jobs" / job_id / spec["frozen_target_path"]
                if sha256(target) != spec["target_source"]["sha256"]:
                    raise ValueError("冻结目标文件已改变，拒绝恢复")
            checked = precheck_resume(spec, self.runtime / "jobs" / job_id)
            if not checked.get("available"):
                raise ValueError("任务尚未保存完整检查点，请使用原配置新建任务")
            state = {key: value for key, value in state.items() if key not in {
                "files", "spec", "summary", "effective_config", "checkpoint", "progress", "timing"}}
            state.update(state="queued", error=None, pid=None, updated_at=time.time())
            _atomic_json(self.runtime / "jobs" / job_id / "status.json", state)
            self.launch(job_id)
            return state

    def stop(self, job_id):
        with self._job_lock:
            state = self.get_job(job_id)
            process = self.processes.get(job_id)
            if state["state"] == "queued" and process is None:
                self._launching_jobs.pop(job_id, None)
                self.pending_jobs.discard(job_id)
                state.update(state="interrupted", error="已取消排队", updated_at=time.time())
            else:
                if process is None or process.poll() is not None:
                    raise ValueError("当前服务没有可停止的活动进程，请从原服务停止")
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=20)
                state.update(state="interrupted", error="用户停止任务，完整个体进度已保留",
                             updated_at=time.time())
                if state.get("kind") == "benchmark":
                    from .benchmark_service import cancel_report
                    cancel_report(self.runtime / "jobs" / job_id, state.get("benchmark_mode"))
                    state["error"] = "测速已停止，已完成方案及报告已保留；未完成方案不支持恢复"
            persisted = {key: value for key, value in state.items() if key not in {
                "files", "spec", "summary", "effective_config", "checkpoint", "progress", "timing"}}
            _atomic_json(self.runtime / "jobs" / job_id / "status.json", persisted)
            return persisted

    def transfer(self, job_id):
        state = self.get_job(job_id)
        if state["kind"] != "pointcloud" or state["state"] != "completed":
            raise ValueError("只能联动已完成的点云任务")
        summary = state.get("summary") or state.get("result") or {}
        if not summary.get("calibration_ready"):
            raise ValueError("六指标尚不能校准：" + "；".join(summary.get("calibration_issues", ["请核对参考基准"])))
        root = self.runtime / "jobs" / job_id / "outputs"
        targets = list(root.rglob("matlab_target.mat"))
        if len(targets) != 1:
            raise ValueError("没有找到唯一的matlab_target.mat")
        with targets[0].open("rb") as stream:
            record = self.upload(f"pointcloud-{job_id}.mat", stream, targets[0].stat().st_size)
        _, path = self.get_upload(record["id"])
        preview = inspect_target(path, "target_data", "rows")
        config = state["spec"].get("pointcloud_config", {})
        return {"upload": record, "preview": preview, "source_job": job_id,
                "geometry": {"space_xy_um": config.get("preprocessing", {}).get("grid_resolution_mm", .05) * 1000}}

    def log_tail(self, job_id, size=60000):
        self.get_job(job_id)
        path = self.runtime / "jobs" / job_id / "worker.log"
        if not path.is_file():
            return ""
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - size))
            return stream.read().decode("utf-8", errors="replace")

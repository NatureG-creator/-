"""任务目录、输入冻结和本机进程管理。"""

from __future__ import annotations

import copy
import io
import json
import os
import shutil
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

UPLOAD_EXTENSIONS = POINT_EXTENSIONS | {".mat", ".xlsx", ".tsv", ".npz"}
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024


def _apdl_control_record(path):
    reason='记录结构无效'
    try:
        if not path.exists(): return {}
        value=json_record(path)
        if isinstance(value,dict) and ('cleanup' not in value or isinstance(value['cleanup'],dict)):
            return value
    except (ValueError,OSError,UnicodeError) as exc:
        reason=f'{type(exc).__name__}: {exc}'
    failure=dict(state='failed',verified_empty=False,
                 error=f'{path.name}控制记录损坏或不可读取：{reason}；需要复核并重试停止。')
    return dict(failure,control_record_error=True,cleanup=dict(failure))


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
            pending_stop=(status.get('kind')=='apdl_tension' and
                          _apdl_control_record(folder/'outputs'/'apdl_stop.json').get('state')=='failed')
            if ((status.get("state") in {"queued", "running", "stop_failed"} or pending_stop) and
                    status.get("pid") in {None, locked_pid} and process_alive(locked_pid)):
                inherited[folder.name] = locked_pid
                inherited_weights[folder.name] = 2 if status.get("kind") in {"benchmark", "diagnostics"} else 1
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
            raise ValueError("文件类型仅支持 TXT、CSV、TSV、XYZ、MAT、XLSX、NPZ")
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

    def benchmark_spec(self, payload, *, retry_snapshot=None):
        from .benchmark import prepare_benchmark
        import numpy as np
        value = copy.deepcopy(payload)
        value.pop("initial_state_info", None)
        value.pop("stage_number", None)
        source = None
        if retry_snapshot:
            source = retry_snapshot["path"]
            value["initial_state_info"] = retry_snapshot["info"]
            value["stage_number"] = retry_snapshot["stage_number"]
        elif value.get("source_job_id"):
            source_id = self.validate_id(value["source_job_id"])
            state = self.get_job(source_id)
            stage = value.get("source_stage")
            if isinstance(stage, bool) or not isinstance(stage, int) or not 1 <= stage <= 100000:
                raise ValueError("source_stage 必须是有效阶段号")
            if state.get("kind") != "simulation" or state.get("state") != "completed":
                raise ValueError("初始表面必须来自已完成的模拟任务")
            source = self.runtime / "jobs" / source_id / "outputs" / f"stage_{stage:03d}.npz"
            if not source.is_file():
                raise ValueError("源任务缺少所选阶段数值文件")
            geometry = state.get("spec", {}).get("config", {}).get("GEOMETRY_CONFIG", {})
            keys = ("grid_w", "grid_l", "grid_n", "space_xy_um", "space_z_um")
            if any(key not in geometry for key in keys):
                raise ValueError("源任务缺少完整几何配置，无法核对物理间距")
            value["initial_state_info"] = {"source_job_id": source_id, "source_stage": stage,
                                          "sha256": sha256(source),
                                          "geometry": {key: geometry[key] for key in keys}}
            value["stage_number"] = stage + 1
        spec = prepare_benchmark(value)
        if source:
            geometry = spec["initial_state_info"].get("geometry", {})
            current = spec["config"]["GEOMETRY_CONFIG"]
            if any(geometry.get(key) != current.get(key) for key in ("space_xy_um", "space_z_um")):
                raise ValueError("源阶段物理间距与本次配置不一致，请采用源网格与物理间距；不进行隐式重采样")
            with np.load(source, allow_pickle=False) as data:
                options = spec["options"]
                expected = (options["grid_w"], options["grid_l"], options["grid_n"] + 1)
                for key, shape in (("perfect_a", expected), ("perfect_d", expected), ("perfect_cl", expected[:2])):
                    if key not in data or data[key].shape != shape or not np.issubdtype(data[key].dtype, np.number) or not np.isfinite(data[key]).all():
                        raise ValueError(f"源阶段{key}形状/数值不匹配，请采用源网格；不进行隐式重采样")
            if sha256(source) != spec["initial_state_info"]["sha256"]:
                raise ValueError("源阶段文件已变化，请重新选择来源")
            spec["initial_state_path"] = "inputs/initial_state.npz"
            spec["scope_note"] = spec["scope_note"].replace("从初始状态开始", "从所选阶段的冻结状态开始")
            spec["scope_note"] += f" 本次从源阶段{spec['stage_number'] - 1}的已冻结状态开始，按阶段{spec['stage_number']}规则评估。"
        return spec, source

    def retry_benchmark(self, job_id, payload):
        previous = self.get_job(job_id)
        if previous.get("kind") != "benchmark" or previous["state"] in {"running", "queued"}:
            raise ValueError("只能对已结束的性能对比新建重试")
        spec = previous["spec"]
        failed = [row["mode"] for row in (previous.get("summary") or {}).get("rows", [])
                  if row["state"] in {"failed", "unavailable", "timeout"}]
        modes = payload.get("modes") or failed or spec["options"]["modes"]
        value = {"kind": "benchmark", "config": copy.deepcopy(spec["config"]),
                 "targets": [spec["target"]], "options": copy.deepcopy(spec["options"])}
        value["options"].update(modes=modes, target_index=0)
        snapshot = None
        if spec.get("initial_state_path"):
            snapshot = {"path": self.runtime / "jobs" / job_id / spec["initial_state_path"],
                        "info": spec["initial_state_info"], "stage_number": spec["stage_number"]}
        return self.create_job(value, benchmark_snapshot=snapshot, retry_of=job_id)

    def create_job(self, payload: dict, *, launch=True, benchmark_snapshot=None, retry_of=None):
        if not isinstance(payload, dict):
            raise ValueError("任务请求必须是对象")
        kind = payload.get("kind")
        if kind not in {"simulation", "pointcloud", "finite_element", "benchmark", "diagnostics", "apdl_tension", "fitting"}:
            raise ValueError("任务类型无效")
        from .task_io import validate_task_io
        io_settings = validate_task_io(payload, self.runtime)
        if kind == "finite_element":
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
        job_id = uuid.uuid4().hex[:16]
        job_dir = self.runtime / "jobs" / job_id
        started = time.perf_counter()
        if kind == "fitting":
            from .fitting_service import prepare_fitting
            spec, fitting_table, fitting_path, fitting_text = prepare_fitting(self, payload)
        elif kind == "apdl_tension":
            from .apdl_service import prepare_apdl
            spec, apdl_sources = prepare_apdl(self,payload)
        elif kind == "benchmark":
            spec, benchmark_source = self.benchmark_spec(payload, retry_snapshot=benchmark_snapshot)
            if retry_of:
                spec["retry_of"] = retry_of
        elif kind == "diagnostics":
            timeout = payload.get("timeout_seconds", 30)
            if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 30:
                raise ValueError("诊断超时必须为1到30秒")
            spec = {"kind": "diagnostics", "timeout_seconds": timeout}
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
        elif kind == "finite_element" and payload.get("upload_id"):
            source_info, source_path = self.get_upload(payload["upload_id"])
            source_kind = payload.get("source_kind")
            expected = {"simulation": ".npz", "measured": ".mat"}.get(source_kind)
            if expected is None or source_path.suffix.lower() != expected:
                raise ValueError("模拟形貌请导入 NPZ，实测表面请导入 MAT（Z_filled / F_filled）")
            if sha256(source_path) != source_info['sha256']:
                raise ValueError('上传文件已被修改，请重新选择文件')
            from .finite_element_export import _read_measured, _state_from_npz
            if source_kind == 'simulation':
                _state_from_npz(source_path)
            else:
                _read_measured(source_path, payload.get('input_variable'))
            spec = {"kind": kind, "source_kind": source_kind, "source_upload": source_info,
                    "source_path": str(source_path), "source_hash": source_info['sha256'],
                    "source_file": source_info['name'], "input_variable": payload.get('input_variable'),
                    "options": options,
                    "reading_seconds": time.perf_counter() - started}
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
            spec = {"kind": kind, "source_job_id": source_job_id, "source_kind": source_kind,
                    "source_path": str(source_path), "source_hash": sha256(source_path),
                    "source_file": source_path.name, "input_variable": payload.get("input_variable"),
                    "options": options, "reading_seconds": time.perf_counter() - started}
        job_dir.mkdir()
        try:
            (job_dir / "inputs").mkdir()
            if kind == "fitting":
                from .fitting_service import freeze_fitting
                freeze_fitting(spec, fitting_table, fitting_path, fitting_text, job_dir)
            if kind == "apdl_tension":
                from .apdl_service import freeze_apdl_sources
                freeze_apdl_sources(apdl_sources,job_dir)
            if kind == "benchmark" and benchmark_source:
                shutil.copy2(benchmark_source, job_dir / spec["initial_state_path"])
                if sha256(job_dir / spec["initial_state_path"]) != spec["initial_state_info"]["sha256"]:
                    raise ValueError("初始阶段快照冻结失败")
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
            _atomic_json(job_dir / "task_io.json", io_settings)
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
        return dict(status, display_name=io_settings['name'] or spec.get('case_name', ''), task_io=io_settings)

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
                benchmark = current.get("kind") in {"benchmark", "diagnostics"}
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
            if state.get('kind')=='apdl_tension':
                # A separate stop record survives a worker's concurrent final
                # status write. Pending cleanup must remain reachable by Stop.
                stop_record=_apdl_control_record(folder/'outputs'/'apdl_stop.json')
                process_record=_apdl_control_record(folder/'outputs'/'mapdl_process.json')
                execution=_apdl_control_record(folder/'outputs'/'mapdl_execution.json')
                cleanup=process_record.get('cleanup') or execution.get('cleanup') or {}
                if stop_record.get('state')=='stopped' and stop_record.get('verified_empty') is True:
                    state.update(state='interrupted',error='APDL任务已停止，已有文件保留；不支持网页续算。')
                    state.pop('stop_error',None)
                elif stop_record.get('state')=='failed' or cleanup.get('state')=='failed':
                    error=stop_record.get('error') or cleanup.get('error') or '求解组尚未确认清理完成'
                    state.update(state='stop_failed',stop_error=error,error=f'停止失败：{error}；可重试停止。')
            if state["state"] in {"queued", "running"}:
                dead_owned = (process is not None and process.poll() is not None and
                              not (state["state"] == "queued" and job_id in self.pending_jobs))
                dead_orphan = process is None and (
                    state["state"] == "running" and not process_alive(state.get("pid")) or
                    state["state"] == "queued" and job_id not in self.pending_jobs)
                if dead_owned or dead_orphan:
                    if state.get('kind')=='apdl_tension':
                        cleanup=self._stop_apdl_group(folder)
                        try: _atomic_json(folder/'outputs'/'apdl_stop.json',cleanup)
                        except Exception as exc: state['stop_persistence_error']=str(exc)
                        state['solver_cleanup']=cleanup
                        if cleanup.get('state')=='failed' or cleanup.get('verified_empty') is not True:
                            state.update(state='stop_failed',stop_error=cleanup.get('error','求解组未确认清空'),
                                         error='APDL工作进程已退出，但求解组清理尚未确认；请重试停止。',updated_at=time.time())
                        else:
                            state.update(state='interrupted',error='APDL工作进程已退出，求解组已清空；已有文件保留，不支持网页续算。',updated_at=time.time())
                            self._record_apdl_stop(folder,cleanup,reason='APDL工作进程异常退出，已有文件保留；结果未完成验收。')
                    else:
                        state.update(state="interrupted", error="任务进程已退出，可检查保存的进度后恢复",
                                     updated_at=time.time())
                    _atomic_json(folder / "status.json", state)
            state["files"] = self.job_files(job_id)
            state["spec"] = json_record(folder / "spec.json", {})
            from .task_io import job_io
            state['task_io'] = job_io(folder, state['spec'])
            state['display_name'] = state['task_io']['name']
            if state.get('export_pending') and not process_alive(state.get('pid')):
                state['export_pending'] = False
                state['task_io']['last_export'] = {'state': 'failed',
                    'error': '成果复制进程已退出，可重新选择目录并导出；原任务成果保留。'}
            state["summary"] = json_record(folder / "outputs" / "summary.json")
            state["effective_config"] = json_record(folder / "outputs" / "effective_config.json")
            state["timing"] = json_record(folder / "outputs" / "timing.json")
            stage_exports = any((folder / "outputs").glob("stage_*.manifest.json")) if (folder / "outputs").is_dir() else False
            checkpoint_exists = (any((folder / "checkpoints").rglob("progress.json"))
                                if (folder / "checkpoints").is_dir() else False)
            state["checkpoint"] = {
                "exists": checkpoint_exists or stage_exports,
                "available": state.get("kind") == "simulation" and
                             state["spec"].get("config", {}).get("mode") in {"strict", "pycharm"} and
                             state["state"] in {"failed", "interrupted"} and (checkpoint_exists or stage_exports),
                "validated": False}
            state["progress"] = {key: state.get(key) for key in (
                "stage", "generation", "maxgen", "completed_individuals", "total_individuals", "phase",
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
        files = [{"name": path.relative_to(root).as_posix(), "bytes": path.stat().st_size}
                for path in sorted(root.rglob("*")) if path.is_file() and
                path.resolve().is_relative_to(root.resolve()) and path.suffix != ".tmp"]
        status = json_record(self.runtime / "jobs" / job_id / "status.json", {})
        if status.get("kind") == "benchmark" and (root / "summary.json").is_file() and not any(f["name"] == "benchmark_bundle.zip" for f in files):
            files.append({"name": "benchmark_bundle.zip", "on_demand": True})
        return files

    def resume(self, job_id):
        with self._job_lock:
            state = self.get_job(job_id)
            spec = state["spec"]
            if spec.get("kind") != "simulation" or spec["config"]["mode"] not in {"strict", "pycharm"}:
                raise ValueError("只有严格或 PyCharm NumPy 模拟支持阶段恢复")
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
            job_dir=self.runtime / "jobs" / job_id
            excluded={"files", "spec", "summary", "effective_config", "checkpoint", "progress", "timing"}
            def persist():
                from .job_status import update_job_status
                persisted={key:value for key,value in state.items() if key not in excluded}
                update_job_status(job_dir/'status.json',persisted,preserve_stop=False)
                return persisted
            if state['state'] not in {'queued','running','stop_failed'}:
                raise ValueError('任务已结束，不能停止；如有清理失败，请查看执行记录。')
            if state["state"] == "queued" and process is None:
                self._launching_jobs.pop(job_id, None)
                self.pending_jobs.discard(job_id)
                state.update(state="interrupted", error="已取消排队", updated_at=time.time())
            else:
                try:
                    from .process_control import verify_worker_process, stop_verified_process
                    apdl=state.get('kind')=='apdl_tension'
                    worker=None
                    if ((process is None and process_alive(state.get('pid'))) or
                            (process is not None and process.poll() is None)):
                        worker=verify_worker_process(job_id,state,job_dir,self.runtime,ROOT)
                    elif not apdl:
                        raise ValueError('任务进程已结束')
                    if apdl:
                        cleanup=self._stop_apdl_group(job_dir)
                        if cleanup.get('state')=='failed': raise ValueError(cleanup.get('error','求解组清理失败'))
                    if worker is not None:
                        stop_verified_process(worker)
                    if process is not None:
                        process.wait(timeout=20)
                    if apdl:
                        cleanup=self._stop_apdl_group(job_dir)
                        if (cleanup.get('state')=='failed' or
                                (cleanup.get('state')!='not_started' and cleanup.get('verified_empty') is not True)):
                            raise ValueError(cleanup.get('error','尚未确认求解进程组为空'))
                        state['solver_cleanup']=cleanup
                        self._record_apdl_stop(job_dir,cleanup)
                        _atomic_json(job_dir/'outputs'/'apdl_stop.json',cleanup)
                except Exception as exc:
                    state.update(state='stop_failed',stop_error=str(exc),
                                 error=f'停止失败：{exc}；尚未确认全部进程退出，可重试停止。',updated_at=time.time())
                    if state.get('kind')=='apdl_tension':
                        try:
                            _atomic_json(job_dir/'outputs'/'apdl_stop.json',dict(state='failed',verified_empty=False,error=str(exc)))
                        except Exception as write_error:
                            state['stop_persistence_error']=str(write_error)
                            exc.add_note(f'停止记录保存失败：{write_error}')
                    try: persist()
                    except Exception as write_error:
                        state['error']+=f'；任务停止状态未能持久化：{write_error}'
                        exc.add_note(f'任务停止状态保存失败：{write_error}')
                    raise ValueError(state['error']) from exc
                state.update(state="interrupted", error="用户停止任务，完整个体进度已保留",
                             updated_at=time.time())
                state.pop('stop_error',None)
                if state.get('kind')=='apdl_tension':
                    state['error']='APDL任务已停止，已有输入、日志与部分输出已保留；未完成结果不可当作完整求解，不支持网页续算。'
                if state.get("kind") == "benchmark":
                    from .benchmark_service import cancel_report
                    cancel_report(self.runtime / "jobs" / job_id, state.get("benchmark_mode"))
                    state["error"] = "测速已停止，已完成方案及报告已保留；未完成方案不支持恢复"
            return persist()

    @staticmethod
    def _stop_apdl_group(job_dir):
        output=job_dir/'outputs'
        execution=_apdl_control_record(output/'mapdl_execution.json')
        if execution.get('control_record_error'):
            return execution['cleanup']
        if not (output/'mapdl_process.json').exists() and execution.get('pid'):
            return dict(state='failed',verified_empty=False,
                        error='旧版任务缺少受控求解组记录，无法核验残留求解进程；请在ANSYS中人工确认。')
        from .apdl_process import stop_owned_execution
        return stop_owned_execution(output)

    @staticmethod
    def _record_apdl_stop(job_dir,cleanup,reason='用户停止APDL任务，已有文件保留；结果未完成验收。'):
        output=job_dir/'outputs'
        summary=json_record(output/'summary.json',{})
        if not summary: return
        now=time.time(); timing=summary.setdefault('timing',{})
        keys={'reading':'reading_seconds','geometry':'geometry_seconds','build':'build_export_seconds',
              'solver':'solver_seconds','postprocess':'postprocess_seconds'}
        for stage,state in summary.get('stage_states',{}).items():
            if state=='running':
                summary['stage_states'][stage]='interrupted'
                started=summary.get('stage_started_at',{}).get(stage)
                if isinstance(started,(int,float)):
                    timing[keys[stage]]=max(0,now-started)
        started=summary.get('started_at')
        if isinstance(started,(int,float)): timing['total_seconds']=max(0,now-started)
        summary.update(solve_state='stopped',solver_cleanup=cleanup,error=reason)
        execution=json_record(output/'mapdl_execution.json')
        if execution: summary.update(solver=execution,execution_record='mapdl_execution.json')
        _atomic_json(output/'timing.json',timing)
        _atomic_json(output/'summary.json',summary)

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

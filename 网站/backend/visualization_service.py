"""Read-only data inspection for the visualization workspace."""
from __future__ import annotations

import csv
import math
import time
import zipfile
from pathlib import Path

import numpy as np
from numpy.lib import format as npformat

from .system_info import sha256

MAX_INSPECT_BYTES = 256 * 1024 * 1024
MAX_TABLE_BYTES = 32 * 1024 * 1024
MAX_PREVIEW_CELLS = 10_000


def _numeric_array(value, label):
    array = np.asarray(value)
    if array.dtype.hasobject or not np.issubdtype(array.dtype, np.number) or np.iscomplexobj(array):
        raise ValueError(f"变量 {label} 不是可预览的实数数值数组")
    if array.ndim not in (2, 3, 4) or not array.size:
        raise ValueError(f"变量 {label} 需要是非空二维矩阵、三维点云或四维阶段数据")
    return array


def _sample(array, stage, variable):
    if array.ndim == 4:
        count = array.shape[0]
        stage = count if stage is None else stage
        if isinstance(stage, bool) or not isinstance(stage, int) or not 1 <= stage <= count:
            raise ValueError(f"阶段必须是 1 至 {count} 的整数")
        array = array[stage - 1]
    elif stage not in (None, 1):
        raise ValueError("该变量不是多阶段数组，阶段只能为 1")
    if array.ndim == 3:
        array = array[:, :, 0]
    rows, columns = array.shape
    stride = max(1, math.ceil(math.sqrt(rows * columns / MAX_PREVIEW_CELLS)))
    sample = np.asarray(array[::stride, ::stride], dtype=np.float64)
    finite = sample[np.isfinite(sample)]
    if not finite.size:
        raise ValueError(f"变量 {variable} 的预览区域没有有限数值")
    return sample, [int(rows), int(columns)], stage, finite


def _inspect_table(path):
    if path.stat().st_size > MAX_TABLE_BYTES:
        raise ValueError("可视化预览目前限制单个文本矩阵不超过 32 MB")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        lines = [line for line in stream if line.strip()]
    first = lines[0] if lines else ""
    if path.suffix.lower() == ".tsv" or ("\t" in first and "," not in first):
        rows = list(csv.reader(lines, delimiter="\t"))
    elif "," in first:
        rows = list(csv.reader(lines, delimiter=","))
    else:
        rows = [line.split() for line in lines]
    rows = [row for row in rows if row and any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("文本文件没有数据行")
    header = False
    try:
        parsed = np.asarray([[float(cell) for cell in row] for row in rows], dtype=np.float64)
    except (ValueError, TypeError):
        if len(rows) < 2:
            raise ValueError("文本文件没有可读取的数值矩阵")
        try:
            parsed = np.asarray([[float(cell) for cell in row] for row in rows[1:]], dtype=np.float64)
        except (ValueError, TypeError) as exc:
            raise ValueError("文本文件包含非数值列；请先导出纯数值矩阵") from exc
        header = True
    if parsed.ndim != 2 or not parsed.size:
        raise ValueError("文本文件必须是规则的二维数值表")
    return parsed, header


def inspect_upload(service, payload):
    started = time.perf_counter()
    upload_id = payload.get("upload_id")
    if not isinstance(upload_id, str):
        raise ValueError("请先上传需要查看的数据文件")
    record, path = service.get_upload(upload_id)
    if sha256(path) != record.get("sha256"):
        raise ValueError("来源文件已变化，请重新上传")
    if path.stat().st_size > MAX_INSPECT_BYTES and path.suffix.lower() != ".npz":
        raise ValueError("可视化预览目前限制文件不超过 256 MB")
    suffix = path.suffix.lower()
    variable, source_shape, stage_count, has_header = "数值矩阵", None, 1, False
    if suffix == ".npz":
        headers = {}
        with zipfile.ZipFile(path) as compressed:
            members = compressed.infolist()
            if len(members) > 4096 or len({item.filename for item in members}) != len(members):
                raise ValueError("NPZ 成员过多或名称重复")
            for member in members:
                if not member.filename.endswith(".npy"):
                    continue
                name = member.filename[:-4]
                with compressed.open(member) as stream:
                    version = npformat.read_magic(stream)
                    if version == (1, 0):
                        shape, _, dtype = npformat.read_array_header_1_0(stream)
                    elif version == (2, 0):
                        shape, _, dtype = npformat.read_array_header_2_0(stream)
                    else:
                        continue
                if (not dtype.hasobject and np.issubdtype(dtype, np.number)
                        and not np.issubdtype(dtype, np.complexfloating)
                        and len(shape) in (2, 3, 4) and math.prod(shape) > 0):
                    headers[name] = {"shape": tuple(shape), "dtype": dtype,
                                     "bytes": math.prod(shape) * dtype.itemsize}
        candidates = list(headers)
        if not candidates:
            raise ValueError("NPZ 中没有可预览的实数二维、三维或四维数组")
        if candidates:
            name = payload.get("variable") or next((key for key in candidates if key in {"perfect_a", "a_sd", "Z_filled", "F_filled"}), candidates[0])
            if name not in headers:
                raise ValueError("所选 NPZ 变量不存在或不是可预览数值数组")
            if headers[name]["bytes"] > MAX_INSPECT_BYTES:
                raise ValueError("所选 NPZ 变量解压后超过 256 MB，暂不生成网页预览")
            with np.load(path, allow_pickle=False) as archive:
                raw = archive[name]
            variable = name
            source_shape = list(raw.shape)
            stage_count = raw.shape[0] if raw.ndim == 4 else 1
            selected_stage = payload.get("stage")
            if selected_stage is not None:
                if isinstance(selected_stage, bool):
                    raise ValueError("阶段必须是整数")
                try:
                    selected_stage = int(selected_stage)
                except (TypeError, ValueError) as exc:
                    raise ValueError("阶段必须是整数") from exc
            array = _numeric_array(raw, variable)
            sample, preview_shape, stage, finite = _sample(array, selected_stage, variable)
            variables = [{"name": key, "shape": list(value["shape"]), "dtype": str(value["dtype"])} for key, value in headers.items()]
    elif suffix == ".mat":
        from scipy.io import loadmat, whosmat
        metadata = [(key, shape, kind) for key, shape, kind in whosmat(path)
                    if len(shape) in (2, 3, 4) and kind in {"double", "single", "uint8", "uint16", "uint32", "uint64", "int8", "int16", "int32", "int64"}]
        candidates = {key: shape for key, shape, _ in metadata}
        if not candidates:
            raise ValueError("MAT 文件中没有可预览的数值变量")
        variable = payload.get("variable") or next((key for key in candidates if key in {"perfect_a", "a_sd", "Z_filled", "F_filled"}), next(iter(candidates)))
        if variable not in candidates:
            raise ValueError("所选 MAT 变量不存在或不是可预览数值数组")
        if math.prod(candidates[variable]) * 8 > MAX_INSPECT_BYTES:
            raise ValueError("所选 MAT 变量解压后超过 256 MB，暂不生成网页预览")
        array = loadmat(path, variable_names=[variable])[variable]
        array = _numeric_array(array, variable)
        source_shape = list(array.shape)
        stage_count = array.shape[0] if array.ndim == 4 else 1
        selected_stage = payload.get("stage")
        if selected_stage is not None:
            try:
                selected_stage = int(selected_stage)
            except (TypeError, ValueError) as exc:
                raise ValueError("阶段必须是整数") from exc
        sample, preview_shape, stage, finite = _sample(array, selected_stage, variable)
        variables = [{"name": key, "shape": list(shape), "dtype": kind} for key, shape, kind in metadata]
    elif suffix in {".csv", ".txt", ".tsv", ".xyz"}:
        if suffix == ".xyz":
            from .pointcloud_runner import inspect_xyz
            pointcloud = inspect_xyz(path)
            sample_points = pointcloud["sample_points"]
            finite_z = np.asarray([point[2] for point in sample_points], dtype=float)
            if sha256(path) != record.get("sha256"):
                raise ValueError("读取期间来源文件变化，请重新上传")
            return {"name": record["name"], "extension": suffix, "bytes": record["bytes"],
                    "variable": "XYZ 坐标", "variables": [{"name": "XYZ 坐标", "shape": [pointcloud["points"], 3], "dtype": "float"}],
                    "source_shape": [pointcloud["points"], 3], "preview_shape": [len(sample_points), 3],
                    "stage": 1, "stage_count": 1, "minimum": min(point[2] for point in sample_points),
                    "maximum": max(point[2] for point in sample_points), "mean": float(np.mean(finite_z)),
                    "preview_finite_count": len(sample_points), "preview": sample_points, "mode": "scatter",
                    "reading_seconds": pointcloud["reading_seconds"],
                    "visualization_note": "XY 平面显示抽样点云；颜色表示 Z 高程，单位 mm。坐标抽样仅用于网页预览，不修改原始点云。",
                    "plot_kind": "scatter", "unit": "mm",
                    "interpretation": "每个点是一个 XYZ 测量点；颜色用于识别高度变化，不代表腐蚀深度。"}
        array, has_header = _inspect_table(path)
        source_shape = list(array.shape)
        sample, preview_shape, stage, finite = _sample(array, None, variable)
        variables = [{"name": variable, "shape": source_shape, "dtype": str(array.dtype)}]
    else:
        raise ValueError("支持 NPZ、MAT、CSV、TXT、TSV、XYZ 文件")
    if sha256(path) != record.get("sha256"):
        raise ValueError("读取期间来源文件变化，请重新上传")
    return {"name": record["name"], "extension": suffix, "bytes": record["bytes"],
            "variable": variable, "variables": variables, "source_shape": source_shape,
            "preview_shape": preview_shape, "stage": stage, "stage_count": stage_count,
            "minimum": float(np.min(finite)), "maximum": float(np.max(finite)),
            "mean": float(np.mean(finite)), "preview_finite_count": int(finite.size),
            "preview": [[float(value) if np.isfinite(value) else None for value in row] for row in sample],
            "sample_stride": max(1, math.ceil(math.sqrt(math.prod(preview_shape) / MAX_PREVIEW_CELLS))),
            "mode": "matrix", "plot_kind": "matrix", "unit": "原始数据单位",
            "header_detected": has_header, "reading_seconds": round(time.perf_counter() - started, 6),
            "visualization_note": "这是数值矩阵预览，不自动解释为腐蚀深度。三维数组展示第 1 层切片；四维数组展示所选阶段切片。",
            "interpretation": "颜色只表示所选变量的数值大小；如需物理形貌，请使用腐蚀演化阶段或 XYZ 点云入口。"}


def _simulation_source(service, job_id):
    service.validate_id(job_id)
    job = service.get_job(job_id)
    if job.get("kind") != "simulation" or job.get("state") != "completed":
        raise ValueError("只能查看已完成的腐蚀模拟任务")
    folder = service.runtime / "jobs" / job_id
    output = folder / "outputs"
    stage_files = {}
    for path in output.glob("stage_*.npz"):
        if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(output.resolve()):
            try:
                stage_files[int(path.stem.split("_")[-1])] = path
            except ValueError:
                continue
    if stage_files:
        stages = sorted(stage_files)
    else:
        path = output / "simulation.npz"
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(output.resolve()):
            raise ValueError("模拟任务没有可读取的阶段 NPZ 文件")
        from .apdl_npz import inspect_npz
        info = inspect_npz(path)
        selected = next(item for item in info["variables"] if item["name"] == info["default_variable"])
        stages = list(range(1, selected["stage_count"] + 1))
        stage_files = {stage: path for stage in stages}
    return job, stage_files, stages


def simulation_sources(service):
    jobs = []
    folders = sorted((service.runtime / "jobs").iterdir(), key=lambda path: path.stat().st_mtime, reverse=True)
    for folder in folders:
        if len(jobs) >= 100 or not folder.is_dir() or len(folder.name) != 16:
            continue
        try:
            job, _, stages = _simulation_source(service, folder.name)
        except (ValueError, FileNotFoundError):
            continue
        jobs.append({"id": folder.name, "name": job.get("display_name") or job.get("case_name") or folder.name,
                     "stages": stages, "stage_count": len(stages)})
    return {"jobs": jobs}


def inspect_simulation_stage(service, payload):
    started = time.perf_counter()
    job_id = payload.get("job_id")
    if not isinstance(job_id, str):
        raise ValueError("请选择一个已完成的腐蚀模拟任务")
    job, stage_files, stages = _simulation_source(service, job_id)
    stage = payload.get("stage")
    if isinstance(stage, bool) or not isinstance(stage, int) or stage not in stage_files:
        raise ValueError("所选阶段在任务结果中不存在")
    path = stage_files[stage]
    from .apdl_npz import inspect_npz, read_npz_state
    info = inspect_npz(path)
    variable = info["default_variable"]
    selected = next(item for item in info["variables"] if item["name"] == variable)
    if math.prod(selected["state_shape"]) * np.dtype(selected["dtype"]).itemsize > MAX_INSPECT_BYTES:
        raise ValueError("该阶段状态超过 256 MB，暂不生成网页预览")
    state, _ = read_npz_state(path, variable, stage if selected["stage_count"] > 1 else 1)
    config = job.get("spec", {}).get("config", {})
    geometry = config.get("GEOMETRY_CONFIG", {})
    space_z = geometry.get("space_z_um") or info.get("geometry", {}).get("space_z_um")
    if not isinstance(space_z, (int, float)) or isinstance(space_z, bool) or not math.isfinite(float(space_z)) or float(space_z) <= 0:
        raise ValueError("任务缺少有效的 Z 向元胞尺寸，无法按原规则换算腐蚀深度")
    engine = Path(__file__).resolve().parents[1] / "engine" / "01_运行程序与数据"
    import sys
    if str(engine) not in sys.path:
        sys.path.insert(0, str(engine))
    from export_apdl_mat import surface_from_ca_state
    surface = surface_from_ca_state(state, float(space_z))
    rows, columns = surface.shape
    stride = max(1, math.ceil(math.sqrt(rows * columns / MAX_PREVIEW_CELLS)))
    sample = np.asarray(surface[::stride, ::stride], dtype=np.float64)
    finite = sample[np.isfinite(sample)]
    max_index = [int(index) for index in np.unravel_index(int(np.nanargmax(surface)), surface.shape)]
    preview_max_index = [min(int(sample.shape[0] - 1), int(round(max_index[0] / stride))),
                         min(int(sample.shape[1] - 1), int(round(max_index[1] / stride)))]
    return {"job_id": job_id, "job_name": job.get("display_name") or job.get("case_name") or job_id,
            "stage": stage, "stage_count": len(stages), "variable": variable,
            "shape": [int(rows), int(columns)], "preview_shape": list(sample.shape),
            "minimum_mm": float(np.min(finite)), "maximum_mm": float(np.max(finite)),
            "mean_mm": float(np.mean(finite)), "preview": sample.tolist(), "sample_stride": stride,
            "reading_seconds": round(time.perf_counter() - started, 6),
            "plot_kind": "surface_depth", "unit": "mm",
            "x_range_mm": [0.0, float(max(columns - 1, 0) * float(geometry.get("space_xy_um") or info.get("geometry", {}).get("space_xy_um") or 1.0) / 1000.0)],
            "y_range_mm": [0.0, float(max(rows - 1, 0) * float(geometry.get("space_xy_um") or info.get("geometry", {}).get("space_xy_um") or 1.0) / 1000.0)],
            "max_position_index": max_index, "max_position_preview_index": preview_max_index,
            "rule": "复用 export_apdl_mat.surface_from_ca_state：沿 Z 找到第一层金属，换算正向腐蚀深度；不改变模拟或提取规则。"}

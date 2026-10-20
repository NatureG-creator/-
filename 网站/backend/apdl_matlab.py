"""二维表面矩阵到 MATLAB APDL X/Y/Z 坐标文件的转换入口。"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import time
from pathlib import Path

from scipy.io import loadmat

from .apdl_coordinates import parse_coordinate_triplet
from .system_info import find_matlab, sha256

SUPPORTED_EXTENSIONS = {".mat", ".csv", ".txt", ".tsv"}
OUTPUT_NAMES = {"x": "DIANYUN_X.txt", "y": "DIANYUN_Y.txt", "z": "DIANYUN_Z.txt"}


def _number(value, label, *, positive=False):
    if isinstance(value, bool):
        raise ValueError(f"{label}必须是有限数值")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是有限数值") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{label}必须是有限数值")
    if positive and number <= 0:
        raise ValueError(f"{label}必须大于 0")
    return number


def _matlab_string(value: str) -> str:
    """Escape a Windows path or variable for a MATLAB single-quoted string."""
    return "'" + str(value).replace("'", "''") + "'"


def inspect_mat_variables(path: Path) -> list[dict]:
    if path.suffix.lower() != ".mat":
        return []
    try:
        values = loadmat(path, variable_names=None)
    except (NotImplementedError, ValueError, OSError):
        matlab = find_matlab()
        if not matlab:
            return []
        expression = (
            "s=whos('-file'," + _matlab_string(str(path.resolve())) + ");"
            "for k=1:numel(s), if numel(s(k).size)==2 && "
            "any(strcmp(s(k).class,{'double','single','uint8','uint16','uint32','uint64','int8','int16','int32','int64'})), "
            "fprintf('%s\\t%d\\t%d\\n',s(k).name,s(k).size(1),s(k).size(2)); end; end;"
        )
        try:
            completed = subprocess.run([matlab, "-batch", expression], capture_output=True,
                                       text=True, encoding="utf-8", errors="replace", timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return []
        result = []
        for line in completed.stdout.splitlines():
            parts = line.strip().split('\t')
            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                result.append({"name": parts[0], "shape": [int(parts[1]), int(parts[2])]})
        return result
    result = []
    for name, value in values.items():
        if name.startswith("__") or getattr(value, "ndim", 0) != 2:
            continue
        if not getattr(value, "dtype", None) or value.dtype.kind not in "fiu":
            continue
        result.append({"name": name, "shape": [int(value.shape[0]), int(value.shape[1])]})
    return result


def _validate_mat_variable(path: Path, requested: str | None) -> str:
    if path.suffix.lower() != ".mat":
        return ""
    candidates = [item["name"] for item in inspect_mat_variables(path)]
    if not candidates and path.suffix.lower() == ".mat":
        # The MATLAB converter can still inspect legacy MAT files when the
        # lightweight upload inspector did not return variable metadata.
        matlab = find_matlab()
        if matlab:
            expression = (
                "s=whos('-file'," + _matlab_string(str(path.resolve())) + ");"
                "for k=1:numel(s), if numel(s(k).size)==2 && "
                "any(strcmp(s(k).class,{'double','single','uint8','uint16','uint32','uint64','int8','int16','int32','int64'})), "
                "fprintf('%s\\t%d\\t%d\\n',s(k).name,s(k).size(1),s(k).size(2)); end; end;"
            )
            try:
                completed = subprocess.run([matlab, "-batch", expression], capture_output=True,
                                           text=True, encoding="utf-8", errors="replace", timeout=120, check=False)
                candidates = [line.split('\t', 1)[0] for line in completed.stdout.splitlines()
                              if line.count('\t') == 2]
            except (OSError, subprocess.TimeoutExpired):
                candidates = []
    preferred = [name for name in ("Z_filled", "F_filled") if name in candidates]
    candidates = preferred or candidates
    variable = str(requested or "")
    if variable:
        if variable not in candidates:
            raise ValueError(f"MAT 中没有指定的二维变量：{variable}")
        return variable
    if len(candidates) != 1:
        raise ValueError("MAT 中存在多个二维数值变量，请先选择要转换的腐蚀 Z 矩阵")
    return candidates[0]


def convert_uploaded_matrix(service, payload: dict) -> dict:
    """调用本机 MATLAB，并将生成的三个坐标文件登记为新的上传记录。"""
    if not isinstance(payload, dict):
        raise ValueError("MATLAB 转换请求必须是对象")
    upload_id = payload.get("upload_id")
    if not isinstance(upload_id, str):
        raise ValueError("必须先上传二维表面矩阵")
    record, source = service.get_upload(upload_id)
    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("MATLAB 转换仅支持 MAT、CSV、TXT、TSV 二维矩阵")
    if sha256(source) != record.get("sha256"):
        raise ValueError("上传矩阵已变化，请重新上传")
    variable = _validate_mat_variable(source, payload.get("variable"))
    dx = _number(payload.get("dx_mm"), "dx_mm", positive=True)
    dy = _number(payload.get("dy_mm"), "dy_mm", positive=True)
    x_start = _number(payload.get("x_start_mm", 0), "x_start_mm")
    y_start = _number(payload.get("y_start_mm", 0), "y_start_mm")
    conversion_mode = payload.get("conversion_mode", "surface_mm")
    if conversion_mode not in ("surface_mm", "baseline_cells"):
        raise ValueError("未知的矩阵转换模式")
    direction = payload.get("coordinate_direction", "front")
    if direction not in ("front", "back"):
        raise ValueError("坐标方向必须是 front 或 back")
    cell_thickness = (_number(payload.get("cell_thickness_mm", .025), "Z 向元胞厚度 / mm", positive=True)
                      if conversion_mode == "baseline_cells" else .025)
    matlab = find_matlab()
    if not matlab:
        raise ValueError("未找到 MATLAB 可执行文件；请设置 MATLAB_BIN 或将 matlab.exe 加入 PATH")

    output_root = service.runtime / "matlab_apdl" / upload_id
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    matlab_dir = Path(__file__).resolve().parents[1] / "matlab"
    expression = (
        f"addpath({_matlab_string(str(matlab_dir.resolve()))});"
        f"matlab_apdl_convert({_matlab_string(str(source.resolve()))},"
        f"{_matlab_string(str(output_root.resolve()))},{_matlab_string(variable)},"
        f"{dx:.17g},{dy:.17g},{x_start:.17g},{y_start:.17g},"
        f"{_matlab_string(conversion_mode)},{cell_thickness:.17g},{_matlab_string(direction)})"
    )
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [matlab, "-batch", expression], cwd=matlab_dir,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("MATLAB 转换超过 600 秒，已停止本次转换") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "MATLAB 未返回错误信息").strip()
        raise ValueError(f"MATLAB 转换失败：{detail[-2000:]}")

    output_paths = {axis: output_root / filename for axis, filename in OUTPUT_NAMES.items()}
    if any(not path.is_file() for path in output_paths.values()):
        raise ValueError("MATLAB 已退出，但没有生成完整的 DIANYUN_X/Y/Z.txt 文件")
    parsed = parse_coordinate_triplet(*(output_paths[axis] for axis in ("x", "y", "z")))
    conversion = json.loads((output_root / "conversion_summary.json").read_text(encoding="utf-8"))
    files = {}
    try:
        for axis, path in output_paths.items():
            data = path.read_bytes()
            files[axis] = service.upload(path.name, io.BytesIO(data), len(data))
    finally:
        shutil.rmtree(output_root, ignore_errors=True)
    return {
        "source_upload_id": upload_id,
        "variable": variable or None,
        "conversion": conversion,
        "shape": parsed["shape"],
        "point_count": parsed["point_count"],
        "dx_mm": parsed["dx_mm"],
        "dy_mm": parsed["dy_mm"],
        "origin_x_mm": parsed["origin_x_mm"],
        "origin_y_mm": parsed["origin_y_mm"],
        "reading_seconds": time.perf_counter() - started,
        "files": {axis: {"id": value["id"], "name": value["name"], "sha256": value["sha256"]}
                  for axis, value in files.items()},
    }

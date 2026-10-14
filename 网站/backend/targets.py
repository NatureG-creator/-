"""读取六指标目标：显式处理变量和方向，绝不默选歧义矩阵。"""
from __future__ import annotations

import csv
import math
import time
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from .config import validate_targets


def _orient(array: np.ndarray, orientation: str) -> np.ndarray:
    if orientation not in {"auto", "rows", "columns"}:
        raise ValueError("目标方向必须是 auto、rows（每行六指标）或 columns（每列六指标）")
    if array.ndim == 1 and array.size == 6:
        array = array.reshape(1, 6)
    if array.ndim != 2:
        raise ValueError("目标矩阵必须为二维 N×6 或 6×N")
    if orientation == "auto":
        if array.shape == (6, 6):
            raise ValueError("6×6矩阵存在方向歧义，请选择 rows 或 columns")
        if array.shape[1] == 6:
            return array
        if array.shape[0] == 6:
            return array.T
    elif orientation == "rows" and array.shape[1] == 6:
        return array
    elif orientation == "columns" and array.shape[0] == 6:
        return array.T
    raise ValueError(f"矩阵尺寸{array.shape}与六指标方向 {orientation} 不匹配")


def _rows(array: np.ndarray) -> list[list[float]]:
    invalid = np.argwhere(~np.isfinite(array))
    if len(invalid):
        row, col = invalid[0]
        raise ValueError(f"目标矩阵第{row+1}行第{col+1}列不是有限数值（NaN或无穷值）")
    result = array.tolist()
    validate_targets(result, "staged")
    return result


def _read_text_rows(path: Path) -> list[list[float]]:
    rows, first_nonempty = [], True
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            fields = next(csv.reader([line])) if "," in line else line.split()
            if len(fields) != 6:
                raise ValueError(f"第{line_no}行不是六列")
            row, invalid = [], []
            for col, item in enumerate(fields, 1):
                try:
                    value = float(item)
                except ValueError:
                    invalid.append(col)
                    continue
                if not math.isfinite(value):
                    raise ValueError(f"第{line_no}行第{col}列不是有限数值（NaN或无穷值）")
                row.append(value)
            if invalid:
                if first_nonempty and len(invalid) == 6:
                    first_nonempty = False
                    continue
                raise ValueError(f"第{line_no}行第{invalid[0]}列不是数值")
            first_nonempty = False
            rows.append(row)
    validate_targets(rows, "staged")
    return rows


def _mat_variables(path: Path) -> dict:
    try:
        return loadmat(path)
    except NotImplementedError as exc:
        raise ValueError("MATLAB v7.3 HDF5 文件暂不支持，请另存为 v7 MAT 或六列CSV") from exc
    except (ValueError, OSError) as exc:
        raise ValueError(f"MAT 文件读取失败：{exc}") from exc


def _metadata_strings(value) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, np.ndarray):
        result = []
        for item in value.ravel():
            result.extend(_metadata_strings(item))
        return result
    return []


def inspect_target(path: Path, variable: str | None = None, orientation: str = "auto") -> dict:
    path, started = Path(path), time.perf_counter()
    if orientation not in {"auto", "rows", "columns"}:
        raise ValueError("目标方向必须是 auto、rows 或 columns")
    suffix = path.suffix.lower()
    result = {"type": "mat" if suffix == ".mat" else "table", "variables": [],
              "selected": None, "shape": None, "targets": [], "issues": [],
              "orientation": orientation}
    if suffix == ".mat":
        values = _mat_variables(path)
        candidates = []
        for name, value in values.items():
            if name.startswith("__"):
                continue
            array = np.asarray(value)
            numeric = array.dtype.kind in "fiu"
            compatible = numeric and array.ndim == 2 and 6 in array.shape and array.size > 0
            result["variables"].append({"name": name, "shape": list(array.shape),
                                        "finite": bool(np.isfinite(array).all()) if numeric else None,
                                        "compatible": bool(compatible)})
            if compatible:
                candidates.append(name)
        selected = variable
        if selected is None:
            if "target_data" in candidates:
                selected = "target_data"
            elif len(candidates) == 1:
                selected = candidates[0]
            elif len(candidates) > 1:
                result["issues"].append("存在多个六指标候选变量，请明确选择变量。")
            else:
                result["issues"].append("MAT文件没有可用的 N×6 或 6×N 数值矩阵。")
        result["selected"] = selected
        if selected is not None:
            if selected not in candidates:
                result["issues"].append(f"MAT文件不存在可用六指标变量：{selected}")
            else:
                result["shape"] = list(np.asarray(values[selected]).shape)
                try:
                    data = _orient(np.asarray(values[selected], dtype=float), orientation)
                    result["shape"] = list(data.shape)
                    result["targets"] = _rows(data)
                except ValueError as exc:
                    result["issues"].append(str(exc))
        if "calibration_ready" in values:
            result["calibration_ready"] = None
            result["calibration_issues"] = _metadata_strings(values.get("calibration_issues", []))
            ready = np.asarray(values["calibration_ready"]).reshape(-1)
            if len(ready) != 1 or ready.dtype.kind not in "biuf" or ready[0] not in (0, 1):
                result["issues"].append("MAT calibration_ready 元数据必须为单个布尔值。")
            else:
                result["calibration_ready"] = bool(ready[0])
                if not bool(ready[0]):
                    result["issues"].append("MAT 标记 calibration_ready=false：物理参考或统计条件未满足，禁止启动校准。")
                    result["issues"].extend(result["calibration_issues"])
    elif suffix in {".csv", ".txt", ".tsv"}:
        if variable:
            result["issues"].append("文本目标不支持 MAT 变量选择。")
        if orientation == "columns":
            result["issues"].append("六列文本目标每行代表一个阶段，请使用 rows 或 auto。")
        try:
            result["targets"] = _read_text_rows(path)
            result["shape"] = [len(result["targets"]), 6]
        except ValueError as exc:
            result["issues"].append(str(exc))
    else:
        raise ValueError("目标文件仅接受 MAT、CSV、TXT、TSV")
    result["reading_seconds"] = round(time.perf_counter() - started, 6)
    return result


def load_targets(path: Path, variable: str | None = None, orientation: str = "auto") -> list[list[float]]:
    info = inspect_target(path, variable, orientation)
    if info["issues"]:
        raise ValueError("；".join(info["issues"]))
    return info["targets"]

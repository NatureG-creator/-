"""Inspect MATLAB and text six-metric targets without guessing dimensions."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from .config import validate_targets


def inspect_target(path: Path) -> dict:
    path = Path(path)
    if path.suffix.lower() == ".mat":
        try:
            variables = loadmat(path, simplify_cells=True)
        except NotImplementedError as exc:
            raise ValueError("MATLAB v7.3 HDF5 文件暂不支持，请另存为 v7 MAT 或六列CSV") from exc
        available = []
        for name, value in variables.items():
            if name.startswith("__"):
                continue
            try:
                array = np.asarray(value, dtype=float)
            except (TypeError, ValueError):
                continue
            if array.ndim == 1 and array.size == 6:
                array = array.reshape(1, 6)
            if array.ndim == 2 and 6 in array.shape:
                available.append({"name": name, "shape": list(array.shape),
                                  "finite": bool(np.isfinite(array).all())})
        if not available:
            raise ValueError("MAT文件没有可用的 N×6 或 6×N 数值矩阵")
        selected = "target_data" if any(item["name"] == "target_data" for item in available) else available[0]["name"]
        return {"type": "mat", "variables": available, "selected": selected}
    if path.suffix.lower() not in {".csv", ".txt", ".tsv"}:
        raise ValueError("目标文件仅接受 MAT、CSV、TXT、TSV")
    rows = _read_text_rows(path)
    return {"type": "table", "shape": [len(rows), 6], "targets": rows}


def _read_text_rows(path: Path) -> list[list[float]]:
    rows = []
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            fields = next(csv.reader([line])) if "," in line else line.split()
            if len(fields) != 6:
                raise ValueError(f"第{line_no}行不是六列")
            try:
                row = [float(item) for item in fields]
            except ValueError as exc:
                if line_no == 1:
                    continue
                raise ValueError(f"第{line_no}行不是数值") from exc
            rows.append(row)
    validate_targets(rows, "staged")
    return rows


def load_targets(path: Path, variable: str | None = None) -> list[list[float]]:
    path = Path(path)
    if path.suffix.lower() != ".mat":
        return _read_text_rows(path)
    info = inspect_target(path)
    name = variable or info["selected"]
    if name not in {item["name"] for item in info["variables"]}:
        raise ValueError(f"MAT文件不存在可用变量：{name}")
    data = np.asarray(loadmat(path, variable_names=[name], simplify_cells=True)[name], dtype=float)
    if data.ndim == 1:
        data = data.reshape(1, 6)
    elif data.shape[1] != 6 and data.shape[0] == 6:
        data = data.T
    rows = data.tolist()
    validate_targets(rows, "staged")
    return rows

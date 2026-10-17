"""MATLAB APDL 坐标文件的严格解析与表面深度转换。"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np


_EXTENSIONS = {".txt", ".csv", ".tsv"}


def _read_vector(path: Path) -> np.ndarray:
    path = Path(path)
    if path.suffix.lower() not in _EXTENSIONS:
        raise ValueError(f"坐标文件 {path.name} 仅支持 TXT、CSV、TSV")
    delimiter = {".csv": ",", ".tsv": "\t"}.get(path.suffix.lower())
    try:
        values = np.loadtxt(path, delimiter=delimiter, encoding="utf-8-sig")
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError(f"坐标文件 {path.name} 必须是无表头的有限数值一列：{exc}") from exc
    values = np.asarray(values)
    if values.ndim == 0:
        values = values.reshape(1)
    elif values.ndim == 2:
        if values.shape[1] != 1:
            raise ValueError(f"坐标文件 {path.name} 必须是一列向量，不能包含多列")
        values = values[:, 0]
    elif values.ndim != 1:
        raise ValueError(f"坐标文件 {path.name} 不是一维坐标向量")
    if values.size < 4:
        raise ValueError(f"坐标文件 {path.name} 至少需要 4 个点")
    if not np.issubdtype(values.dtype, np.number) or not np.isrealobj(values):
        raise ValueError(f"坐标文件 {path.name} 必须是实数")
    values = values.astype(np.float64, copy=False)
    if not np.isfinite(values).all():
        raise ValueError(f"坐标文件 {path.name} 包含 NaN/Inf，坐标必须有限")
    return values


def _canonical(values: np.ndarray) -> np.ndarray:
    """吸收 MATLAB 文本输出的末位误差，同时保留毫米级坐标精度。"""
    return np.round(values, decimals=12)


def _regular_axis(values: np.ndarray, label: str) -> tuple[np.ndarray, float]:
    axis = np.unique(_canonical(values))
    if axis.size < 2:
        raise ValueError(f"{label} 坐标至少需要两个不同位置")
    differences = np.diff(axis)
    spacing = float(np.median(differences))
    if spacing <= 0 or not np.allclose(differences, spacing, rtol=1e-8, atol=1e-12):
        raise ValueError(f"{label} 坐标间距不规则，不能无插值恢复结构化网格")
    return axis, spacing


def parse_coordinate_triplet(x_path, y_path, z_path) -> dict:
    """恢复 MATLAB 展平坐标为 ``[Y, X]`` 网格。"""
    paths = [Path(x_path), Path(y_path), Path(z_path)]
    x, y, z = (_read_vector(path) for path in paths)
    if not (x.size == y.size == z.size):
        raise ValueError("X、Y、Z 坐标文件长度不一致，不能组成同一表面网格")
    x_axis, dx = _regular_axis(x, "X")
    y_axis, dy = _regular_axis(y, "Y")
    expected = int(x_axis.size * y_axis.size)
    if x.size != expected:
        raise ValueError(f"XY 坐标不构成完整规则网格：实际 {x.size} 点，期望 {expected} 点")

    x_grid = np.empty((y_axis.size, x_axis.size), dtype=np.float64)
    y_grid = np.empty_like(x_grid)
    z_grid = np.empty_like(x_grid)
    occupied: set[tuple[float, float]] = set()
    x_values = _canonical(x)
    y_values = _canonical(y)
    for x_value, y_value, z_value in zip(x_values, y_values, z, strict=True):
        key = (float(x_value), float(y_value))
        if key in occupied:
            raise ValueError("XY 坐标存在重复点，不能恢复唯一网格")
        occupied.add(key)
        ix = int(np.searchsorted(x_axis, x_value))
        iy = int(np.searchsorted(y_axis, y_value))
        if ix >= x_axis.size or iy >= y_axis.size:
            raise ValueError("XY 坐标超出恢复后的规则轴范围")
        x_grid[iy, ix] = x_value
        y_grid[iy, ix] = y_value
        z_grid[iy, ix] = z_value
    if len(occupied) != expected or not np.isfinite(z_grid).all():
        raise ValueError("XY 坐标存在缺点或 Z 坐标非有限值，不能恢复完整网格")
    if not np.allclose(x_grid, x_axis[None, :], rtol=0, atol=1e-12):
        raise ValueError("X 坐标行不一致，输入不是规则矩形网格")
    if not np.allclose(y_grid, y_axis[:, None], rtol=0, atol=1e-12):
        raise ValueError("Y 坐标列不一致，输入不是规则矩形网格")
    lattice = np.column_stack((x_grid.ravel(order="C"), y_grid.ravel(order="C")))
    lattice_signature = hashlib.sha256(lattice.astype("<f8", copy=False).tobytes()).hexdigest()
    return {
        "shape": [int(y_axis.size), int(x_axis.size)],
        "x_grid": x_grid,
        "y_grid": y_grid,
        "z_grid": z_grid,
        "dx_mm": dx,
        "dy_mm": dy,
        "origin_x_mm": float(x_axis[0]),
        "origin_y_mm": float(y_axis[0]),
        "x_range_mm": [float(x_axis[0]), float(x_axis[-1])],
        "y_range_mm": [float(y_axis[0]), float(y_axis[-1])],
        "point_count": int(x.size),
        "xy_grid_sha256": lattice_signature,
    }


def surface_depth(parsed: dict, direction: str) -> np.ndarray:
    """Convert absolute Z coordinates to positive inward corrosion depth."""
    if direction not in {"front", "back"}:
        raise ValueError("坐标表面方向只能是 front 或 back")
    z = np.asarray(parsed.get("z_grid"))
    if z.ndim != 2 or z.size == 0 or not np.isfinite(z).all():
        raise ValueError("坐标表面缺少有限二维 Z 网格")
    if direction == "front":
        depth = float(z.max()) - z
    else:
        depth = z - float(z.min())
    if np.any(depth < -1e-12):
        raise ValueError("坐标转换得到负腐蚀深度，请检查表面方向")
    return np.maximum(depth, 0.0).astype(np.float64, copy=True)


def validate_coordinate_pair(top: dict, bottom: dict) -> None:
    """Ensure two surfaces share exactly the same XY sampling lattice."""
    if top.get("shape") != bottom.get("shape"):
        raise ValueError("双面坐标行列数不一致，不能隐式重采样")
    for key in ("x_grid", "y_grid"):
        if not np.allclose(top[key], bottom[key], rtol=0, atol=1e-10):
            raise ValueError("双面坐标 XY 网格不一致，不能确认配准")
    for key in ("dx_mm", "dy_mm", "origin_x_mm", "origin_y_mm"):
        if not math.isclose(float(top[key]), float(bottom[key]), rel_tol=0, abs_tol=1e-10):
            raise ValueError("双面坐标间距或原点不一致，不能确认配准")
    if top.get("xy_grid_sha256") != bottom.get("xy_grid_sha256"):
        raise ValueError("双面坐标 XY 网格签名不一致，不能确认配准")

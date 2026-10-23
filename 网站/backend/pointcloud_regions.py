"""Export rectangular crops from the already processed measured surface."""

from __future__ import annotations

import math
import secrets
from pathlib import Path

import numpy as np
from scipy.io import loadmat, savemat


def export_region(job_dir: Path, axis: str, length_mm: float, center_mm: float | None = None) -> dict:
    if axis not in {"X", "Y"}:
        raise ValueError("裁剪方向只能选择X或Y")
    try:
        length_mm = float(length_mm)
        center_mm = None if center_mm is None else float(center_mm)
    except (TypeError, ValueError) as exc:
        raise ValueError("裁剪长度和中心坐标必须是数字") from exc
    if not math.isfinite(length_mm) or length_mm <= 0:
        raise ValueError("裁剪长度必须是有限正数")
    source = Path(job_dir) / "outputs" / "pointcloud" / "measured_surface_smoothed.mat"
    if not source.is_file():
        raise ValueError("任务没有可裁剪的已处理实测点云")
    data = loadmat(source)
    height = np.asarray(data["height_matrix_mm"], dtype=float)
    depth = np.asarray(data["corrosion_depth_matrix_mm"], dtype=float)
    x = np.asarray(data["x_coordinates_mm"], dtype=float).reshape(-1)
    y = np.asarray(data["y_coordinates_mm"], dtype=float).reshape(-1)
    if height.ndim != 2 or depth.shape != height.shape or height.shape != (y.size, x.size):
        raise ValueError("已处理点云的高程、腐蚀深度和X/Y坐标尺寸不匹配")
    if not np.isfinite(height).all() or not np.isfinite(depth).all():
        raise ValueError("已处理点云包含非有限高程或腐蚀深度")
    if x.size < 2 or y.size < 2 or not np.all(np.diff(x) > 0) or not np.all(np.diff(y) > 0):
        raise ValueError("已处理点云的X/Y坐标必须至少包含两个递增网格点")
    coordinates = x if axis == "X" else y
    if center_mm is None:
        center_mm = float((coordinates[0] + coordinates[-1]) / 2)
    low, high = center_mm - length_mm / 2, center_mm + length_mm / 2
    keep = (coordinates >= low) & (coordinates <= high)
    indices = np.flatnonzero(keep)
    if indices.size < 2:
        raise ValueError("该区域不足两个网格点；请增大长度或调整中心坐标")
    if axis == "X":
        height, depth, x = height[:, indices], depth[:, indices], x[indices]
    else:
        height, depth, y = height[indices, :], depth[indices, :], y[indices]
    xx, yy = np.meshgrid(x, y)
    xyz = np.column_stack((xx.ravel(), yy.ravel(), height.ravel()))
    region_id = secrets.token_hex(6)
    folder = source.parent / "regions" / region_id
    folder.mkdir(parents=True, exist_ok=False)
    savemat(folder / "processed_region.mat", {
        "height_matrix_mm": height, "corrosion_depth_matrix_mm": depth,
        "x_coordinates_mm": x, "y_coordinates_mm": y,
        "processed_xyz_mm": xyz,
    }, do_compression=True)
    table = np.column_stack((xyz, depth.ravel()))
    np.savetxt(folder / "processed_region.csv", table, delimiter=",",
               header="x_mm,y_mm,height_mm,relative_corrosion_depth_mm", comments="", fmt="%.9g")
    np.savetxt(folder / "processed_region.xyz", xyz, delimiter=" ", fmt="%.9g")
    return {
        "region_id": region_id, "axis": axis, "requested_length_mm": length_mm,
        "requested_range_mm": [low, high],
        "actual_range_mm": [float(coordinates[indices[0]]), float(coordinates[indices[-1]])],
        "center_mm": center_mm, "shape": list(height.shape), "point_count": int(xyz.shape[0]),
        "corrosion_depth_range_mm": [float(depth.min()), float(depth.max())],
        "coordinate_origin": "analysis_local_origin", "files": [
            f"pointcloud/regions/{region_id}/processed_region.mat",
            f"pointcloud/regions/{region_id}/processed_region.csv",
            f"pointcloud/regions/{region_id}/processed_region.xyz",
        ], "preview_xyz": xyz[::max(1, math.ceil(len(xyz) / 2500))].tolist(),
        "preview_depth_mm": depth.ravel()[::max(1, math.ceil(len(depth.ravel()) / 2500))].tolist(),
    }

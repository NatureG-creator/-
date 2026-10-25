"""Export rectangular crops from the already processed measured surface."""

from __future__ import annotations

import json
import math
import secrets
from pathlib import Path

import numpy as np
from scipy.io import loadmat, savemat

from .pointcloud_preview import grid_preview


def export_region(job_dir: Path, axis: str, length_mm: float, center_mm: float | None = None,
                  source_kind: str = "pointcloud", side: str | None = None,
                  variant: str = "raw", *, width_mm: float | None = None,
                  center_x_mm: float | None = None, center_y_mm: float | None = None,
                  specimen_length_mm: float | None = None,
                  specimen_width_mm: float | None = None,
                  specimen_thickness_mm: float | None = None,
                  confirmation: dict | None = None) -> dict:
    if axis not in {"X", "Y"}:
        raise ValueError("裁剪方向只能选择X或Y")
    try:
        length_mm = float(length_mm)
        center_mm = None if center_mm is None else float(center_mm)
    except (TypeError, ValueError) as exc:
        raise ValueError("裁剪长度和中心坐标必须是数字") from exc
    if not math.isfinite(length_mm) or length_mm <= 0:
        raise ValueError("裁剪长度必须是有限正数")
    job_dir = Path(job_dir)
    empirical_reference = None
    if source_kind == "common_reference":
        from .pointcloud_view import _common_preview
        status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
        spec = json.loads((job_dir / "spec.json").read_text(encoding="utf-8"))
        if spec.get("kind") != "pointcloud" or status.get("state") != "completed":
            raise ValueError("共同坐标裁剪只接受已完成的点云任务")
        if not isinstance(confirmation, dict) or width_mm is None:
            raise ValueError("请先确认共同坐标裁剪范围")
        common = _common_preview(job_dir, spec)["common_reference"]
        empirical_reference = {key: common[key] for key in (
            "cache_key", "complete_surface_sha256", "depth_sha256", "reference_height_mm",
            "reference_column_count", "reference_ratio", "original_thickness_mm",
            "physical_pristine_reference_verified")}
        if confirmation.get("reference") != empirical_reference:
            raise ValueError("预览来源或20%经验参考链已变化，请重新预览并确认")
    if source_kind == "pointcloud":
        source = job_dir / "outputs" / "pointcloud" / "measured_surface_smoothed.mat"
        output_root = source.parent
        region_root = output_root
        if not source.is_file():
            raise ValueError("任务没有可裁剪的已处理点云")
        data = loadmat(source) if source.is_file() else {}
        height = np.asarray(data.get("height_matrix_mm", []), dtype=float)
        depth = np.asarray(data.get("corrosion_depth_matrix_mm", []), dtype=float)
        x = np.asarray(data.get("x_coordinates_mm", []), dtype=float).reshape(-1)
        y = np.asarray(data.get("y_coordinates_mm", []), dtype=float).reshape(-1)
        coordinate_origin = "analysis_local_origin"
        value_mode = "height"
        depth_source = "relative_to_full_surface_max"
    elif source_kind in {"reference190", "common_reference"}:
        source = job_dir / "outputs" / "pointcloud" / "reference_surface_190mm.mat"
        output_root = source.parent
        region_root = output_root
        if not source.is_file():
            raise ValueError("任务没有完整190 mm参考表面结果")
        data = loadmat(source)
        height = np.asarray(data.get("height_matrix_mm", []), dtype=float)
        x = np.asarray(data.get("x_coordinates_mm", []), dtype=float).reshape(-1)
        y = np.asarray(data.get("y_coordinates_mm", []), dtype=float).reshape(-1)
        depth = None
        coordinate_origin = ("verified_common_scan_coordinates" if empirical_reference else
                             "independently_levelled_full_reference_scan")
        value_mode = "height"
        depth_source = None
    elif source_kind == "surface_generation":
        if side not in {"front", "back"} or variant not in {"raw", "smoothed"}:
            raise ValueError("独立表面裁剪需指定正/反面及原始/平滑版本")
        suffix = "_smoothed" if variant == "smoothed" else ""
        output_root = job_dir / "outputs"
        region_root = output_root / side
        manifest = output_root / side / f"manifest{suffix}.json"
        if not manifest.is_file():
            raise ValueError("该任务没有指定的独立表面结果")
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        source = output_root / side / f"{metadata['output_variable']}{suffix}.mat"
        if not source.is_file():
            raise ValueError("指定的独立点云 MAT 文件不存在")
        data = loadmat(source) if source.is_file() else {}
        variable = metadata["output_variable"]
        height = np.asarray(data.get(variable, []), dtype=float)
        x = float(metadata["origin_x_mm"]) + np.arange(height.shape[1]) * float(metadata["dx_mm"])
        y = float(metadata["origin_y_mm"]) + np.arange(height.shape[0]) * float(metadata["dy_mm"])
        value_mode = metadata.get("value_mode", "height")
        depth = height if value_mode == "depth" else None
        depth_source = "input_depth_matrix" if depth is not None else None
        coordinate_origin = "generated_surface_coordinates"
    else:
        raise ValueError("不支持的已处理点云来源")
    if not source.is_file():
        raise ValueError("任务没有可裁剪的已处理点云")
    if height.ndim != 2 or (depth is not None and depth.shape != height.shape) or height.shape != (y.size, x.size):
        raise ValueError("点云数值矩阵、腐蚀深度和X/Y坐标尺寸不匹配")
    if not np.isfinite(height).all() or (depth is not None and not np.isfinite(depth).all()):
        raise ValueError("点云包含非有限数值")
    if x.size < 2 or y.size < 2 or not np.all(np.diff(x) > 0) or not np.all(np.diff(y) > 0):
        raise ValueError("已处理点云的X/Y坐标必须至少包含两个递增网格点")
    def optional_positive(value, label):
        if value is None or value == "":
            return None
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}必须是正数") from exc
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{label}必须是正数")
        return value

    specimen = {
        "length_mm": optional_positive(specimen_length_mm, "试件长度"),
        "width_mm": optional_positive(specimen_width_mm, "试件宽度"),
        "thickness_mm": optional_positive(specimen_thickness_mm, "试件厚度"),
    }
    # Legacy one-axis requests remain supported; new requests select an X/Y rectangle.
    source_x_bounds = [float(x[0]), float(x[-1])]
    source_y_bounds = [float(y[0]), float(y[-1])]
    if width_mm is None:
        selected_axis = x if axis == "X" else y
        if center_mm is None:
            center_mm = float((selected_axis[0] + selected_axis[-1]) / 2)
        low, high = center_mm - length_mm / 2, center_mm + length_mm / 2
        keep = (selected_axis >= low) & (selected_axis <= high)
        indices = np.flatnonzero(keep)
        if indices.size < 2:
            raise ValueError("该区域不足两个网格点；请增大长度或调整中心坐标")
        if axis == "X":
            height, x = height[:, indices], x[indices]
            if depth is not None:
                depth = depth[:, indices]
            center_x_mm = center_mm
            center_y_mm = float((y[0] + y[-1]) / 2) if center_y_mm is None else center_y_mm
            requested_x, requested_y = [low, high], [float(y[0]), float(y[-1])]
        else:
            height, y = height[indices, :], y[indices]
            if depth is not None:
                depth = depth[indices, :]
            center_y_mm = center_mm
            center_x_mm = float((x[0] + x[-1]) / 2) if center_x_mm is None else center_x_mm
            requested_x, requested_y = [float(x[0]), float(x[-1])], [low, high]
    else:
        width_mm = optional_positive(width_mm, "裁剪宽度")
        center_x_mm = float((x[0] + x[-1]) / 2) if center_x_mm is None else float(center_x_mm)
        center_y_mm = float((y[0] + y[-1]) / 2) if center_y_mm is None else float(center_y_mm)
        if not math.isfinite(center_x_mm) or not math.isfinite(center_y_mm):
            raise ValueError("区域中心坐标必须是有限数值")
        requested_x = [center_x_mm - length_mm / 2, center_x_mm + length_mm / 2]
        requested_y = [center_y_mm - width_mm / 2, center_y_mm + width_mm / 2]
        ix = np.flatnonzero((x >= requested_x[0]) & (x <= requested_x[1]))
        iy = np.flatnonzero((y >= requested_y[0]) & (y <= requested_y[1]))
        if ix.size < 2 or iy.size < 2:
            raise ValueError("裁剪区域在X或Y方向不足两个网格点；请增大尺寸或调整中心坐标")
        height = height[np.ix_(iy, ix)]
        if depth is not None:
            depth = depth[np.ix_(iy, ix)]
        x, y = x[ix], y[iy]
    xx, yy = np.meshgrid(x, y)
    xyz = np.column_stack((xx.ravel(), yy.ravel(), height.ravel()))
    if empirical_reference:
        expected = {"requested_bounds_mm": {"x": requested_x, "y": requested_y},
                    "actual_bounds_mm": {"x": [float(x[0]), float(x[-1])],
                                         "y": [float(y[0]), float(y[-1])]},
                    "shape": list(height.shape), "point_count": int(xyz.shape[0])}
        if any(confirmation.get(key) != value for key, value in expected.items()):
            raise ValueError("裁剪参数或节点范围与确认时不一致，请重新确认")
    region_id = secrets.token_hex(6)
    folder = region_root / "regions" / region_id
    folder.mkdir(parents=True, exist_ok=False)
    savemat(folder / "processed_region.mat", {
        "height_matrix_mm": height, "z_value_mode": value_mode,
        "corrosion_depth_matrix_mm": depth if depth is not None else np.empty((0, 0)),
        "depth_source": depth_source or "not_calibrated",
        "x_coordinates_mm": x, "y_coordinates_mm": y,
        "processed_xyz_mm": xyz,
        **({"empirical_reference_json": json.dumps(empirical_reference, ensure_ascii=False)}
           if empirical_reference else {}),
    }, do_compression=True)
    table = np.column_stack((xyz, depth.ravel())) if depth is not None else xyz
    np.savetxt(folder / "processed_region.csv", table, delimiter=",",
               header="x_mm,y_mm,z_mm,corrosion_depth_mm" if depth is not None else "x_mm,y_mm,z_mm",
               comments="", fmt="%.9g")
    np.savetxt(folder / "processed_region.xyz", xyz, delimiter=" ", fmt="%.9g")
    actual_x = [float(x[0]), float(x[-1])]
    actual_y = [float(y[0]), float(y[-1])]
    x_coverage = min(source_x_bounds[1], requested_x[1]) - max(source_x_bounds[0], requested_x[0])
    y_coverage = min(source_y_bounds[1], requested_y[1]) - max(source_y_bounds[0], requested_y[0])
    coverage = max(0.0, x_coverage) * max(0.0, y_coverage) / (
        (requested_x[1] - requested_x[0]) * (requested_y[1] - requested_y[0]))
    metadata = {
        "source_kind": source_kind, "region_id": region_id,
        "specimen_dimensions_mm": specimen,
        "requested_bounds_mm": {"x": requested_x, "y": requested_y},
        "actual_bounds_mm": {"x": actual_x, "y": actual_y},
        "geometric_coverage_fraction": min(1.0, max(0.0, coverage)),
        "grid_shape_rows_y_columns_x": list(height.shape),
        "grid_point_count": int(xyz.shape[0]),
        "depth_semantics": ("independent reference surface; no calibrated corrosion depth"
                            if source_kind in {"reference190", "common_reference"} else
                            "relative_to_full_surface_max; not verified pristine-reference depth"
                            if source_kind == "pointcloud" else
                            "input depth matrix; reference provenance depends on source"
                            if depth is not None else "not calibrated"),
    }
    if empirical_reference:
        metadata["empirical_reference"] = empirical_reference
        metadata["depth_semantics"] = "original common-frame H; fixed 20% empirical reference recorded; no depth recalibration"
    (folder / "region_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    preview_xyz, preview_depth = grid_preview(x, y, height, depth)
    return {
        "region_id": region_id, "axis": axis, "requested_length_mm": length_mm,
        "requested_range_mm": requested_x if width_mm is None and axis == "X" else requested_y if width_mm is None else None,
        "actual_range_mm": actual_x if width_mm is None and axis == "X" else actual_y if width_mm is None else None,
        "requested_bounds_mm": {"x": requested_x, "y": requested_y},
        "actual_bounds_mm": {"x": actual_x, "y": actual_y},
        "geometric_coverage_fraction": min(1.0, max(0.0, coverage)),
        "specimen_dimensions_mm": specimen,
        "center_mm": center_mm, "center_x_mm": center_x_mm, "center_y_mm": center_y_mm,
        "shape": list(height.shape), "point_count": int(xyz.shape[0]),
        "corrosion_depth_available": depth is not None,
        "corrosion_depth_range_mm": [float(depth.min()), float(depth.max())] if depth is not None else None,
        "depth_source": depth_source,
        "depth_semantics": (metadata["depth_semantics"] if empirical_reference else
                            "independent reference surface; no calibrated corrosion depth"
                            if source_kind == "reference190" else
                            "full_surface_max_minus_height; not verified pristine-reference depth"
                            if source_kind == "pointcloud" else
                            "input depth matrix; reference provenance depends on source"
                            if depth is not None else "not calibrated"),
        **({"empirical_reference": empirical_reference} if empirical_reference else {}),
        "coordinate_origin": coordinate_origin, "files": [
            f"{folder.relative_to(job_dir / 'outputs').as_posix()}/processed_region.mat",
            f"{folder.relative_to(job_dir / 'outputs').as_posix()}/processed_region.csv",
            f"{folder.relative_to(job_dir / 'outputs').as_posix()}/processed_region.xyz",
            f"{folder.relative_to(job_dir / 'outputs').as_posix()}/region_metadata.json",
        ], "preview_xyz": preview_xyz.tolist(),
        "preview_depth_mm": preview_depth.tolist() if preview_depth is not None else [],
    }

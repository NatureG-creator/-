"""Corrosion morphology and section-loss parameters for fracture calibration.

The CA state keeps an initial non-metal surface layer at Python index 0.
All physical thickness and section calculations therefore use ``a[:, :, 1:]``.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np

from .geometry import PaperGeometry


def _physical_metal_mask(a_output: np.ndarray) -> np.ndarray:
    """Return physical metal cells, excluding the CA initial surface layer."""
    a = np.asarray(a_output)
    if a.ndim != 3 or a.shape[2] < 2:
        raise ValueError("a_output must be a 3D CA array with a surface layer and physical layers")
    return a[:, :, 1:] == 1


def compute_section_metrics(a_output: np.ndarray, geometry: PaperGeometry) -> dict[str, float | str]:
    """Calculate the paper's section-damage factor ``ds``.

    MATLAB uses ``sum(sum(sum(a_output==1)))`` for remaining material. Python
    uses ``np.count_nonzero(metal)`` after removing the index-0 surface layer,
    which is not part of the physical thickness.

    The paper's definition is:
    ``ds = (Save - Smin) / Save * 100``.
    """
    metal = _physical_metal_mask(a_output)

    model_thickness_um = geometry.model_thickness_um(metal.shape[2])
    intact_extra_thickness_um = max(geometry.plate_thickness_um - model_thickness_um, 0.0)
    yz_cell_area_um2 = geometry.space_xy_um * geometry.space_z_um
    intact_x_section_um2 = geometry.model_length_um(metal.shape[1]) * intact_extra_thickness_um
    intact_y_section_um2 = geometry.model_width_um(metal.shape[0]) * intact_extra_thickness_um

    # MATLAB 1-based sections along x/y become Python 0-based station arrays.
    # For a section normal to x, each remaining cell contributes dy*dz.
    x_section_areas_um2 = (
        np.sum(metal, axis=(1, 2), dtype=np.int64).astype(float) * yz_cell_area_um2
        + intact_x_section_um2
    )
    # For a section normal to y, each remaining cell contributes dx*dz.
    y_section_areas_um2 = (
        np.sum(metal, axis=(0, 2), dtype=np.int64).astype(float) * yz_cell_area_um2
        + intact_y_section_um2
    )
    save_x_um2 = float(np.mean(x_section_areas_um2))
    smin_x_um2 = float(np.min(x_section_areas_um2))
    ds_x_fraction = (save_x_um2 - smin_x_um2) / save_x_um2 if save_x_um2 > 0 else float("nan")
    save_y_um2 = float(np.mean(y_section_areas_um2))
    smin_y_um2 = float(np.min(y_section_areas_um2))
    ds_y_fraction = (save_y_um2 - smin_y_um2) / save_y_um2 if save_y_um2 > 0 else float("nan")
    if ds_y_fraction >= ds_x_fraction:
        control_direction = "y"
        save_um2 = save_y_um2
        smin_um2 = smin_y_um2
        ds_fraction = ds_y_fraction
    else:
        control_direction = "x"
        save_um2 = save_x_um2
        smin_um2 = smin_x_um2
        ds_fraction = ds_x_fraction

    # Paper Eq. (4): ds = (Save - Smin) / Save * 100.
    ds = ds_fraction * 100.0

    return {
        "control_direction": control_direction,
        "smin_um2": smin_um2,
        "save_um2": save_um2,
        "ds_fraction": float(ds_fraction),
        "ds": float(ds),
    }


def _surface_depth_cells(metal: np.ndarray) -> np.ndarray:
    """Get corrosion depth in cell counts, with uncorroded surface equal to 0."""
    has_metal = np.any(metal, axis=2)
    first_metal_index = np.argmax(metal, axis=2)
    # NumPy index is 0-based; unlike MATLAB `find`, zero here means no loss.
    return np.where(has_metal, first_metal_index, metal.shape[2]).astype(np.float64)


def _label_connected_2d(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Label 8-neighbor 2D regions, falling back when SciPy cannot load."""
    try:
        from scipy import ndimage  # type: ignore

        return ndimage.label(mask, structure=np.ones((3, 3), dtype=np.int8))
    except Exception:
        labels = np.zeros(mask.shape, dtype=np.int32)
        current = 0
        rows, cols = mask.shape
        neighbors = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        for r in range(rows):
            for c in range(cols):
                if not mask[r, c] or labels[r, c] != 0:
                    continue
                current += 1
                stack = [(r, c)]
                labels[r, c] = current
                while stack:
                    cr, cc = stack.pop()
                    for dr, dc in neighbors:
                        nr, nc = cr + dr, cc + dc
                        if 0 <= nr < rows and 0 <= nc < cols and mask[nr, nc] and labels[nr, nc] == 0:
                            labels[nr, nc] = current
                            stack.append((nr, nc))
        return labels, current


def _pit_records(depth_cells: np.ndarray, geometry: PaperGeometry) -> list[dict[str, float]]:
    """Identify connected corroded surface areas and compute equivalent diameters."""
    labels, count = _label_connected_2d(depth_cells > 0)
    records: list[dict[str, float]] = []
    for pit_id in range(1, count + 1):
        mask = labels == pit_id
        area_cells = int(np.count_nonzero(mask))
        values = depth_cells[mask]
        max_depth_cells = float(np.max(values))
        diameter_cells = math.sqrt(4.0 * area_cells / math.pi)
        depth_um = geometry.depth_um(max_depth_cells)
        diameter_um = geometry.diameter_um(diameter_cells)
        records.append(
            {
                "pit_id": pit_id,
                "area_um2": geometry.area_um2(area_cells),
                "depth_um": depth_um,
                "diameter_um": diameter_um,
                "rho": depth_um / diameter_um if diameter_um > 0 else float("nan"),
            }
        )
    return records


def compute_fracture_parameters(
    a_output: np.ndarray,
    geometry: PaperGeometry,
) -> tuple[dict[str, float | str], list[dict[str, float]]]:
    """Extract `ds`, `lambda`, `rho`, and `lambda_rho` from one CA result."""
    metal = _physical_metal_mask(a_output)
    metrics = compute_section_metrics(a_output, geometry)
    depth_cells = _surface_depth_cells(metal)
    pit_details = _pit_records(depth_cells, geometry)

    metrics["plate_thickness_um"] = float(geometry.plate_thickness_um)
    if pit_details:
        deepest = max(pit_details, key=lambda item: item["depth_um"])
        metrics["hmax_um"] = float(deepest["depth_um"])
        metrics["d_at_hmax_um"] = float(deepest["diameter_um"])
        metrics["rho_at_hmax"] = float(deepest["rho"])
    else:
        metrics["hmax_um"] = 0.0
        metrics["d_at_hmax_um"] = float("nan")
        metrics["rho_at_hmax"] = float("nan")

    metrics["lambda"] = metrics["hmax_um"] / geometry.plate_thickness_um
    metrics["lambda_rho"] = metrics["lambda"] * metrics["rho_at_hmax"]
    return metrics, pit_details


def write_parameter_exports(
    output_dir: str | Path,
    metrics: dict[str, float | str],
    pit_details: list[dict[str, float]],
) -> dict[str, Path]:
    """Write aggregate and per-pit parameter tables for spreadsheet or fitting use."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "fracture_morphology_parameters.csv"
    json_path = output / "fracture_morphology_parameters.json"
    pits_path = output / "fracture_pit_details.csv"

    export_fields = [
        "control_direction",
        "plate_thickness_um",
        "smin_um2",
        "save_um2",
        "ds_fraction",
        "ds",
        "hmax_um",
        "d_at_hmax_um",
        "rho_at_hmax",
        "lambda",
        "lambda_rho",
        "source_npz",
    ]
    export_metrics = {key: metrics[key] for key in export_fields if key in metrics}
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(export_metrics.keys()))
        writer.writeheader()
        writer.writerow(export_metrics)
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(export_metrics, handle, ensure_ascii=False, indent=2, allow_nan=True)
    pit_fields = ["pit_id", "area_um2", "depth_um", "diameter_um", "rho"]
    with pits_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=pit_fields)
        writer.writeheader()
        writer.writerows(
            {key: pit[key] for key in pit_fields}
            for pit in pit_details
        )
    return {"csv": csv_path, "json": json_path, "pits_csv": pits_path}

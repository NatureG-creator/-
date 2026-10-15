"""Finite-element surface export helpers.

This module only adapts an already computed surface to the APDL input contract.
It does not change the CA, GA, MATLAB metrics, or checkpoint algorithms.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.io import loadmat, savemat


ALLOWED_VARIABLES = {"Z_filled", "F_filled"}
ALLOWED_KINDS = {"simulation", "measured"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_surface_matrix(value: object) -> np.ndarray:
    """Return a finite 2-D float matrix or raise a clear validation error."""
    array = np.asarray(value)
    if array.ndim != 2 or array.size == 0 or not np.issubdtype(array.dtype, np.number):
        raise ValueError(f"表面数据必须是非空二维数值矩阵，当前形状为 {array.shape}。")
    array = np.asarray(array, dtype=np.float64)
    if not np.isfinite(array).all():
        raise ValueError("表面数据包含 NaN 或 Inf。")
    return array


def _read_measured(path: Path, variable: str | None) -> tuple[str, np.ndarray]:
    if not path.is_file():
        raise FileNotFoundError(f"实测表面 MAT 不存在：{path}")
    values = loadmat(path)
    selected = variable
    if selected:
        if selected not in ALLOWED_VARIABLES:
            raise ValueError("输入变量只能是 Z_filled 或 F_filled。")
        if selected not in values:
            raise KeyError(f"{path.name} 中不存在变量 {selected}。")
    else:
        selected = next((name for name in ("Z_filled", "F_filled") if name in values), None)
    if selected is None:
        raise KeyError(f"{path.name} 未找到 Z_filled 或 F_filled。")
    return selected, validate_surface_matrix(values[selected])


def _state_from_npz(path: Path) -> np.ndarray:
    if not path.is_file():
        raise FileNotFoundError(f"模拟结果 NPZ 不存在：{path}")
    with np.load(path, allow_pickle=False) as data:
        if "perfect_a" in data.files:
            state = np.asarray(data["perfect_a"])
        elif "a_sd" in data.files:
            state = np.asarray(data["a_sd"])
            if state.ndim == 4:
                state = state[-1]
        else:
            raise KeyError(f"{path.name} 未找到 perfect_a 或 a_sd。")
    if state.ndim != 3 or not np.issubdtype(state.dtype, np.number) or not np.isfinite(state).all():
        raise ValueError("CA 状态必须是有限三维数值数组。")
    return state


def surface_from_ca_state(state: np.ndarray, space_z_um: float) -> np.ndarray:
    """Extract positive corrosion depth in mm from the first metal layer."""
    if not np.isscalar(space_z_um) or not np.isfinite(float(space_z_um)) or float(space_z_um) <= 0:
        raise ValueError("space_z_um 必须是正的有限数值。")
    state = np.asarray(state)
    if state.ndim != 3:
        raise ValueError(f"CA 状态必须是三维数组，当前为 {state.shape}。")
    metal = state == 1
    has_metal = np.any(metal, axis=2)
    first_metal = np.argmax(metal, axis=2).astype(np.float64)
    max_depth_layer = state.shape[2] - 1
    depth_layer = np.where(has_metal, first_metal, float(max_depth_layer))
    return depth_layer * float(space_z_um) / 1000.0


def _write_surface_csv(path: Path, matrix: np.ndarray) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        for row in matrix:
            writer.writerow([f"{float(value):.12g}" for value in row])


def _write_coordinates(path: Path, matrix: np.ndarray, *, spacing: float,
                       origin_x: float, origin_y: float, precision: str) -> None:
    try:
        formatter = precision % 1.0
    except (TypeError, ValueError):
        raise ValueError("precision 必须是类似 %.6f 的格式字符串。")
    if not np.isfinite(spacing) or spacing <= 0:
        raise ValueError("grid_spacing_mm 必须是正的有限数值。")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["row", "column", "x_mm", "y_mm", "depth_mm"])
        for row in range(matrix.shape[0]):
            for column in range(matrix.shape[1]):
                writer.writerow([row, column,
                                 precision % (origin_x + row * spacing),
                                 precision % (origin_y + column * spacing),
                                 precision % float(matrix[row, column])])


def _write_preview(path: Path, matrix: np.ndarray, variable: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    fig, axis = plt.subplots(figsize=(7, 4.5))
    try:
        image = axis.imshow(matrix.T, origin="lower", aspect="auto", cmap="viridis")
        axis.set(xlabel="X index", ylabel="Y index", title=f"{variable} surface")
        fig.colorbar(image, ax=axis, label="depth / mm")
        fig.tight_layout()
        fig.savefig(path, dpi=160)
    finally:
        plt.close(fig)


def create_surface_bundle(source_kind: str, source_file: str | Path,
                          output_dir: str | Path, options: dict) -> dict:
    """Create APDL-compatible MAT/CSV/manifest/ZIP files for one surface."""
    if source_kind not in ALLOWED_KINDS:
        raise ValueError("source_kind 只能是 simulation 或 measured。")
    source = Path(source_file).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    options = dict(options or {})
    output_variable = str(options.get("output_variable") or ("F_filled" if source_kind == "simulation" else "Z_filled"))
    if output_variable not in ALLOWED_VARIABLES:
        raise ValueError("output_variable 只能是 Z_filled 或 F_filled。")
    if source_kind == "simulation":
        matrix = surface_from_ca_state(_state_from_npz(source), float(options.get("space_z_um", 25.0)))
        input_variable = None
    else:
        input_variable, matrix = _read_measured(source, options.get("input_variable"))
    matrix = validate_surface_matrix(matrix)
    spacing = float(options.get("grid_spacing_mm", 0.05))
    origin_x = float(options.get("origin_x_mm", 0.0))
    origin_y = float(options.get("origin_y_mm", 0.0))
    precision = str(options.get("precision", "%.6f"))
    if not np.isfinite(origin_x) or not np.isfinite(origin_y):
        raise ValueError("坐标原点必须是有限数值。")

    mat_path = output / f"{output_variable}.mat"
    csv_path = output / "surface.csv"
    coordinate_path = output / "coordinates.csv"
    manifest_path = output / "finite_element_manifest.json"
    zip_path = output / "finite_element_input_bundle.zip"
    savemat(mat_path, {output_variable: matrix}, do_compression=False, long_field_names=True)
    _write_surface_csv(csv_path, matrix)
    _write_coordinates(coordinate_path, matrix, spacing=spacing, origin_x=origin_x,
                       origin_y=origin_y, precision=precision)
    preview_path = output / "surface_preview.png"
    _write_preview(preview_path, matrix, output_variable)

    files = [mat_path, csv_path, coordinate_path]
    if preview_path.is_file():
        files.append(preview_path)
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {"kind": source_kind, "path": str(source), "sha256": _sha256(source),
                   "input_variable": input_variable},
        "output_variable": output_variable,
        "shape": [int(matrix.shape[0]), int(matrix.shape[1])],
        "value_range_mm": [float(np.min(matrix)), float(np.max(matrix))],
        "options": {"space_z_um": float(options.get("space_z_um", 25.0)),
                    "grid_spacing_mm": spacing, "origin_x_mm": origin_x,
                    "origin_y_mm": origin_y, "precision": precision},
        "files": [],
        "rules": "simulation uses first metal layer; measured preserves source matrix without resampling.",
    }
    for path in files:
        manifest["files"].append({"name": path.name, "bytes": path.stat().st_size,
                                  "sha256": _sha256(path)})
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    files.append(manifest_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for path in files:
            archive.write(path, path.name)
    return {"output_variable": output_variable, "shape": manifest["shape"],
            "value_range_mm": manifest["value_range_mm"], "source": manifest["source"],
            "files": [item["name"] for item in manifest["files"]] + [zip_path.name],
            "manifest": manifest_path.name, "zip": zip_path.name}


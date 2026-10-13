"""Post-processing helpers converted from MATLAB surface-analysis scripts."""

from __future__ import annotations

import numpy as np
from unified_config import POSTPROCESS_CONFIG
from scipy import ndimage
from skimage import filters, morphology, segmentation

from .ca import first_metal_depth


def moving_avg_3d(
    a: np.ndarray, window_size: int, w: int, l: int, n: int, gaussian_sigma: float | None = None
) -> tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    """Python version of `moving_avg_3D.m`."""
    depth_map = first_metal_depth(a, w, l, n)
    data = depth_map
    if gaussian_sigma is None:
        gaussian_sigma = float(POSTPROCESS_CONFIG["gaussian_sigma"])
    smoothed_data = filters.gaussian(data, sigma=gaussian_sigma, preserve_range=True)
    half_win = window_size // 2
    data_ext = np.pad(smoothed_data, ((half_win, half_win), (half_win, half_win)), "symmetric")
    kernel = np.ones((window_size, window_size), dtype=np.float64) / (window_size**2)
    baseline_ext = ndimage.convolve(data_ext, kernel, mode="constant", cval=0.0)
    baseline = baseline_ext[half_win : half_win + w, half_win : half_win + l]
    corrected_data = data - baseline
    original_peaks = morphology.local_maxima(data)
    corrected_peaks = morphology.local_maxima(corrected_data)
    denom = np.sum(original_peaks)
    retention_ratio = float(np.sum(corrected_peaks) / denom) if denom else 0.0
    return baseline, smoothed_data, retention_ratio, depth_map


def expand_matrix(original_matrix: np.ndarray, factor: int) -> np.ndarray:
    """Python version of `expandMatrix.m` using nearest-neighbor repeat."""
    if factor == 1:
        return np.array(original_matrix, copy=True)
    return np.repeat(np.repeat(original_matrix, factor, axis=0), factor, axis=1)


def find_local_extrema(
    data: np.ndarray,
    min_prominence: float = 0.001,
    min_distance: int = 20,
    neighborhood: tuple[int, int] = (35, 35),
) -> tuple[np.ndarray, np.ndarray]:
    """Nested `find_local_extrema` from `jixiantiqu_3D.m`."""
    max_locs: list[list[int]] = []
    max_vals: list[float] = []
    min_locs: list[list[int]] = []
    min_vals: list[float] = []
    nh_radius = (neighborhood[0] // 2, neighborhood[1] // 2)
    rows, cols = data.shape
    for i in range(rows):
        for j in range(cols):
            row_start = max(0, i - nh_radius[0])
            row_stop = min(rows, i + nh_radius[0] + 1)
            col_start = max(0, j - nh_radius[1])
            col_stop = min(cols, j + nh_radius[1] + 1)
            region = data[row_start:row_stop, col_start:col_stop]
            center = data[i, j]
            region_mean = float(np.mean(region))
            prominence = abs(center - region_mean)
            if center == np.max(region) and center > region_mean and prominence >= min_prominence:
                max_locs.append([i + 1, j + 1])
                max_vals.append(float(center))
            if center == np.min(region) and center < region_mean and prominence >= min_prominence:
                min_locs.append([i + 1, j + 1])
                min_vals.append(float(center))
    max_arr = _apply_nms(np.array(max_locs, dtype=np.int64), np.array(max_vals), min_distance, "desc")
    min_arr = _apply_nms(np.array(min_locs, dtype=np.int64), np.array(min_vals), min_distance, "asc")
    return max_arr, min_arr


def _apply_nms(locs: np.ndarray, vals: np.ndarray, min_distance: int, order: str) -> np.ndarray:
    if locs.size == 0 or min_distance <= 0:
        return locs.reshape(0, 2) if locs.size == 0 else locs
    sort_idx = np.argsort(vals)
    if order == "desc":
        sort_idx = sort_idx[::-1]
    keep = np.ones(locs.shape[0], dtype=bool)
    accepted: list[np.ndarray] = []
    for idx in sort_idx:
        if accepted:
            dists = np.sqrt(np.sum((locs[idx] - np.vstack(accepted)) ** 2, axis=1))
            if np.any(dists < min_distance):
                keep[idx] = False
                continue
        accepted.append(locs[idx])
    return locs[keep, :]


def watershed_boundaries(
    surface_data: np.ndarray, max_locs: np.ndarray, threshold: float
) -> tuple[np.ndarray, list[np.ndarray]]:
    """Python version of `fenshuiling_boundry.m`."""
    markers = np.zeros(surface_data.shape, dtype=np.int32)
    for k, (r, c) in enumerate(max_locs, start=1):
        # 索引改动：max_locs 为 MATLAB 1-based，Python 数组访问减 1。
        markers[r - 1, c - 1] = k
    if max_locs.size == 0:
        return np.zeros(surface_data.shape, dtype=bool), []
    smoothed_data = filters.gaussian(surface_data, sigma=1.5, preserve_range=True)
    gy, gx = np.gradient(smoothed_data)
    gradient_mag = np.hypot(gx, gy)
    local_mean = ndimage.uniform_filter(surface_data, size=5)
    local_sq_mean = ndimage.uniform_filter(surface_data**2, size=5)
    local_contrast = np.sqrt(np.maximum(local_sq_mean - local_mean**2, 0.0))
    min_height_diff = 0.01 * local_contrast
    gradient_mag = gradient_mag.copy()
    gradient_mag[gradient_mag < min_height_diff] = 255
    distance = ndimage.distance_transform_edt(markers == 0)
    max_distance = float(np.max(distance))
    background = distance > threshold * max_distance if max_distance > 0 else np.zeros_like(distance, dtype=bool)
    markers[background] = 255
    labels = segmentation.watershed(gradient_mag, markers=markers, watershed_line=True)
    boundary_coords: list[np.ndarray] = []
    for r, c in max_locs:
        if r > labels.shape[0] or c > labels.shape[1]:
            boundary_coords.append(np.empty((0, 3), dtype=np.float64))
            continue
        region_label = labels[r - 1, c - 1]
        region_mask = labels == region_label
        boundary = segmentation.find_boundaries(region_mask, mode="outer")
        rows, cols = np.nonzero(boundary)
        heights = surface_data[rows, cols]
        # MATLAB `coords = B{1}(:, [2 1])` gives x,y in 1-based coordinates.
        coords = np.column_stack([cols + 1, rows + 1, heights])
        boundary_coords.append(coords.astype(np.float64))
    return labels == 0, boundary_coords


def pit_metrics(
    data: np.ndarray, pits: list[np.ndarray], max_locs: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Python version of `fushikengtiqu.m`."""
    num_pits = len(pits)
    depths = np.zeros(num_pits, dtype=np.float64)
    ratios = np.zeros(num_pits, dtype=np.float64)
    diameters = np.zeros(num_pits, dtype=np.float64)
    reference = float(np.min(data))
    for k in range(num_pits):
        if k >= max_locs.shape[0] or pits[k].size == 0:
            depths[k] = 1.0
            ratios[k] = 1.0
            diameters[k] = 1.0
            continue
        r, c = max_locs[k]
        depths[k] = data[r - 1, c - 1] - reference + 1.0
        width_x = np.ptp(pits[k][:, 0]) + 1.0
        width_y = np.ptp(pits[k][:, 1]) + 1.0
        diameters[k] = (width_x + width_y) * 0.5
        ratios[k] = depths[k] / diameters[k] if diameters[k] != 0 else 0.0
    return depths, ratios, diameters


def jixiantiqu_3d(
    surface_data: np.ndarray,
    n: int,
    params: dict[str, object] | None,
    threshold: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[np.ndarray]]:
    """Python version of `jixiantiqu_3D.m`."""
    params = {} if params is None else params
    max_locs, min_locs = find_local_extrema(
        surface_data,
        min_prominence=float(params.get("MinProminence", 0.001)),
        min_distance=int(params.get("MinDistance", 20)),
        neighborhood=tuple(params.get("Neighborhood", (35, 35))),
    )
    boundaries, boundary_coords = watershed_boundaries(surface_data, max_locs, threshold)
    depths, ratios, diameters = pit_metrics(surface_data, boundary_coords, max_locs)
    return depths, ratios, diameters, max_locs, min_locs, boundaries, boundary_coords


def safe_log(values: np.ndarray, fallback: float = 1.0) -> np.ndarray:
    """Compute log after replacing non-positive or empty values."""
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        arr = np.array([fallback], dtype=np.float64)
    arr = np.where(arr <= 0, fallback, arr)
    return np.log(arr)


def normfit_sigma(values: np.ndarray) -> float:
    """Return sigma equivalent to MATLAB `normfit` for non-empty samples."""
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size <= 1:
        return 0.0
    return float(np.std(arr, ddof=1))

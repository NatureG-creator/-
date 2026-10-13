from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
from scipy import ndimage, stats
from scipy.optimize import curve_fit
from scipy.spatial.distance import cdist
from skimage import filters, measure, morphology, segmentation, transform

try:
    from taichi_accel import boundary_update_taichi, init_taichi_accel
except Exception:  # pragma: no cover
    boundary_update_taichi = None
    init_taichi_accel = None


def init_taichi(arch: str = "gpu") -> bool:
    """启用 Taichi 加速；失败时自动回退 NumPy/SciPy。"""
    if init_taichi_accel is None:
        print("Taichi 加速模块不可用，继续使用 NumPy/SciPy。")
        return False
    ok = init_taichi_accel(arch)
    print("Taichi 已启用。" if ok else "Taichi 启用失败，继续使用 NumPy/SciPy。")
    return ok


@dataclass
class Block:
    a: np.ndarray
    d: np.ndarray
    cl: np.ndarray


def _as_rng(seed: Optional[int] = None) -> np.random.Generator:
    return np.random.default_rng(seed)


def latin_begin(nind: int, lind: int, bits_per_param: int, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    rng = rng or _as_rng()
    population = np.empty((nind, lind), dtype=float)
    for j in range(lind):
        population[:, j] = (rng.permutation(nind) + rng.random(nind)) / nind

    scaled = np.rint(population * (2**bits_per_param - 1)).astype(np.uint32)
    chrom = np.zeros((nind, lind * bits_per_param), dtype=np.uint8)
    for j in range(lind):
        vals = scaled[:, j]
        for k in range(bits_per_param):
            chrom[:, j * bits_per_param + k] = (vals >> (bits_per_param - k - 1)) & 1
    return chrom


def er2shi(chrom: np.ndarray, lb: Iterable[float], ub: Iterable[float], bits_per_param: int) -> np.ndarray:
    lb = np.asarray(lb, dtype=float)
    ub = np.asarray(ub, dtype=float)
    nind = chrom.shape[0]
    lind = len(lb)
    xy = np.zeros((nind, lind), dtype=float)
    weights = 2 ** np.arange(bits_per_param - 1, -1, -1, dtype=np.uint32)
    for j in range(lind):
        bits = chrom[:, j * bits_per_param : (j + 1) * bits_per_param]
        ints = bits @ weights
        xy[:, j] = lb[j] + (ub[j] - lb[j]) * ints / (2**bits_per_param - 1)
    return xy


def tournament_selection(
    fitness: np.ndarray,
    n_selection: int,
    tournament_size: int,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    rng = rng or _as_rng()
    fitness = np.asarray(fitness).reshape(-1)
    nind = len(fitness)
    tournament_size = min(max(1, tournament_size), nind)
    selected = []
    for _ in range(n_selection):
        for _attempt in range(100):
            candidates = rng.choice(nind, size=tournament_size, replace=False)
            if not any(c in selected for c in candidates):
                break
        selected.append(candidates[np.argmax(fitness[candidates])])
    return np.asarray(selected, dtype=int)


def jiaocha(sel_ch_1: np.ndarray, px: float, lind: int, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    rng = rng or _as_rng()
    nind, chrom_len = sel_ch_1.shape
    bits_per_param = chrom_len // lind
    shuffled_indices = rng.permutation(nind)
    children = sel_ch_1[shuffled_indices].copy()
    for i in range(0, nind - 1, 2):
        if rng.random() < px:
            param_idx = rng.integers(0, lind)
            bit_in_param = rng.integers(1, bits_per_param + 1)
            point = param_idx * bits_per_param + bit_in_param - 1
            tmp = children[i, point:].copy()
            children[i, point:] = children[i + 1, point:]
            children[i + 1, point:] = tmp
    restored = np.empty_like(children)
    restored[shuffled_indices] = children
    return restored


def mut(sel_ch_2: np.ndarray, pm: float, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    rng = rng or _as_rng()
    out = sel_ch_2.copy()
    mask = rng.random(out.shape) < pm
    out[mask] = 1 - out[mask]
    return out


def expand_matrix(original_matrix: np.ndarray, n: int) -> np.ndarray:
    if n == 1:
        return original_matrix.copy()
    return transform.resize(
        original_matrix,
        (original_matrix.shape[0] * n, original_matrix.shape[1] * n),
        order=0,
        preserve_range=True,
        anti_aliasing=False,
    ).astype(original_matrix.dtype, copy=False)


def detect_boundry_3d(a: np.ndarray, n: int) -> np.ndarray:
    if a.ndim != 3:
        raise ValueError("输入 a 必须是 3 维数组")
    if not np.any(a == 0):
        return np.empty((0, 3), dtype=int)

    zero_mask = a == 0
    z_layers = np.where(np.any(zero_mask, axis=(0, 1)))[0]
    if len(z_layers) == 0:
        return np.empty((0, 3), dtype=int)
    process_depth = min(z_layers[-1] + 2, n + 1, a.shape[2])

    a_process = a[:, :, :process_depth]
    non_zero = a_process != 0
    se = np.zeros((3, 3, 3), dtype=bool)
    se[1, 1, 0] = se[1, 1, 2] = True
    se[1, 0, 1] = se[1, 2, 1] = True
    se[0, 1, 1] = se[2, 1, 1] = True
    expanded_zero = ndimage.binary_dilation(~non_zero, structure=se)
    boundary_mask = non_zero & expanded_zero
    return np.argwhere(boundary_mask)


def depth_map_from_a(a: np.ndarray, n: Optional[int] = None) -> np.ndarray:
    n = a.shape[2] - 1 if n is None else n
    metal = a == 1
    has_metal = metal.any(axis=2)
    first = metal.argmax(axis=2).astype(float)
    first[~has_metal] = n + 1
    return first


def tuweipolie(a: np.ndarray, w: int, l: int, p_o: float, max_gaocha: float, n: int):
    depth_map = depth_map_from_a(a, n)[:w, :l]
    gaocha = float(depth_map.max() - depth_map.min())
    if gaocha >= 2:
        threshold = 0.05 * gaocha + depth_map.min()
        points = np.argwhere(depth_map >= threshold)
        p_xiugai = (gaocha / max_gaocha) * (p_o - 1) + 1 if gaocha <= max_gaocha else p_o
        return points, p_xiugai
    return np.empty((0, 2), dtype=int), 1.0


def spread_corrosion(
    x: int,
    y: int,
    z: int,
    a: np.ndarray,
    p_h: float,
    p_v: float,
    n: int,
    cl: np.ndarray,
    cl_threshold: float,
    rng: Optional[np.random.Generator] = None,
):
    rng = rng or _as_rng()
    dirs = [(0, -1, 0, p_h), (0, 1, 0, p_h), (-1, 0, 0, p_h), (1, 0, 0, p_h), (0, 0, -1, p_v), (0, 0, 1, p_v)]
    w, l = a.shape[:2]
    for dx, dy, dz, base_prob in dirs:
        ni, nj, nk = x + dx, y + dy, z + dz
        if 0 <= ni < w and 0 <= nj < l and 0 <= nk < n:
            prob = base_prob * 0.5 * (1 + cl[ni, nj] / cl_threshold)
            if rng.random() < prob and a[ni, nj, nk] == 1:
                a[ni, nj, nk] = 0
    return a, cl


def basic_spread(
    x: int,
    y: int,
    z: int,
    a: np.ndarray,
    p_h: float,
    p_v: float,
    n: int,
    cl: np.ndarray,
    cl_threshold: float,
    w: Optional[int] = None,
    l: Optional[int] = None,
    rng: Optional[np.random.Generator] = None,
):
    return spread_corrosion(x, y, z, a, p_h, p_v, n, cl, cl_threshold, rng)


def enhanced_spread(
    x: int,
    y: int,
    z: int,
    a: np.ndarray,
    p_h: float,
    p_v: float,
    n: int,
    cl: np.ndarray,
    cl_threshold: float,
    w: Optional[int] = None,
    l: Optional[int] = None,
    rng: Optional[np.random.Generator] = None,
):
    rng = rng or _as_rng()
    w = a.shape[0] if w is None else w
    l = a.shape[1] if l is None else l
    offsets = np.array([(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1) if (i, j, k) != (0, 0, 0)])
    for dx, dy, dz in offsets:
        ni, nj, nk = x + dx, y + dy, z + dz
        if not (0 <= ni < w and 0 <= nj < l and 0 <= nk < n):
            continue
        dist = np.linalg.norm([dx, dy, dz])
        if np.isclose(dist, 1):
            base_prob = max(p_h, p_v)
        elif np.isclose(dist, np.sqrt(2)):
            base_prob = 0.7 * max(p_h, p_v)
        else:
            base_prob = 0.4 * max(p_h, p_v)
        cl_factor = min((cl[ni, nj] / cl_threshold) ** 2, 1.0)
        if rng.random() < base_prob * (1 + cl_factor) and a[ni, nj, nk] == 1:
            a[ni, nj, nk] = 0
            cl[ni, nj] = min(cl[ni, nj] + 0.5, cl_threshold)
            if rng.random() < 0.15:
                a, cl = spread_corrosion_3d(ni, nj, nk, a, p_h * 0.9, p_v * 0.9, n, cl, cl_threshold, rng)
    return a, cl


def spread_corrosion_3d(
    x: int,
    y: int,
    z: int,
    a: np.ndarray,
    p_h: float,
    p_v: float,
    n: int,
    cl: np.ndarray,
    cl_threshold: float,
    enhanced_mode: bool = False,
    rng: Optional[np.random.Generator] = None,
):
    if enhanced_mode:
        return enhanced_spread(x, y, z, a, p_h, p_v, n, cl, cl_threshold, rng=rng)
    return basic_spread(x, y, z, a, p_h, p_v, n, cl, cl_threshold, rng=rng)


def spread_corrosion2(
    x: int,
    y: int,
    z: int,
    a: np.ndarray,
    p_h: float,
    p_v: float,
    n: int,
    cl: np.ndarray,
    cl_threshold: float,
    rng: Optional[np.random.Generator] = None,
):
    rng = rng or _as_rng()
    w, l = a.shape[:2]
    offsets = np.array([(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1) if (i, j, k) != (0, 0, 0)])
    for dx, dy, dz in offsets:
        ni, nj, nk = x + dx, y + dy, z + dz
        if not (0 <= ni < w and 0 <= nj < l and 0 <= nk < n):
            continue
        dist = np.linalg.norm([dx, dy, dz])
        if np.isclose(dist, 1):
            base_prob = max(p_h, p_v)
        elif np.isclose(dist, np.sqrt(2)):
            base_prob = 0.6 * max(p_h, p_v)
        else:
            base_prob = 0.3 * max(p_h, p_v)
        prob = base_prob * (1 + (cl[ni, nj] / cl_threshold) ** 2)
        if rng.random() < prob and a[ni, nj, nk] == 1:
            a[ni, nj, nk] = 0
            cl[ni, nj] = min(cl[ni, nj] + 1, cl_threshold)
            if rng.random() < 0.8:
                a, cl = spread_corrosion(ni, nj, nk, a, p_h, p_v, n, cl, cl_threshold, rng)
    return a, cl


def moving_avg_3d(a: np.ndarray, window_size: int, w: int, l: int, n: int):
    depth_map = depth_map_from_a(a, n)[:w, :l]
    smoothed_data = filters.gaussian(depth_map, sigma=1, preserve_range=True)
    half = window_size // 2
    data_ext = np.pad(smoothed_data, ((half, half), (half, half)), mode="symmetric")
    kernel = np.ones((window_size, window_size), dtype=float) / (window_size**2)
    baseline_ext = ndimage.convolve(data_ext, kernel, mode="constant", cval=0.0)
    baseline = baseline_ext[half:-half, half:-half] if half else baseline_ext
    corrected = depth_map - baseline
    original_peaks = morphology.local_maxima(depth_map)
    corrected_peaks = morphology.local_maxima(corrected)
    denom = max(int(original_peaks.sum()), 1)
    retention_ratio = corrected_peaks.sum() / denom
    return baseline, smoothed_data, retention_ratio, depth_map


def find_local_extrema(data: np.ndarray, params: Optional[dict] = None):
    params = params or {}
    min_prom = params.get("MinProminence", 0.001)
    min_dist = int(params.get("MinDistance", 20))
    neighborhood = np.asarray(params.get("Neighborhood", [35, 35]), dtype=int)
    radius = neighborhood // 2

    max_locs, max_vals, min_locs, min_vals = [], [], [], []
    for i in range(data.shape[0]):
        r0, r1 = max(0, i - radius[0]), min(data.shape[0], i + radius[0] + 1)
        for j in range(data.shape[1]):
            c0, c1 = max(0, j - radius[1]), min(data.shape[1], j + radius[1] + 1)
            region = data[r0:r1, c0:c1]
            center = data[i, j]
            prominence = abs(center - region.mean())
            if center == region.max() and center > region.mean() and prominence >= min_prom:
                max_locs.append((i, j))
                max_vals.append(center)
            if center == region.min() and center < region.mean() and prominence >= min_prom:
                min_locs.append((i, j))
                min_vals.append(center)

    def nms(locs, vals, reverse):
        if not locs:
            return np.empty((0, 2), dtype=int)
        locs = np.asarray(locs, dtype=int)
        order = np.argsort(vals)
        if reverse:
            order = order[::-1]
        keep = np.ones(len(locs), dtype=bool)
        chosen = []
        for idx in order:
            if any(np.linalg.norm(locs[idx] - locs[j]) < min_dist for j in chosen):
                keep[idx] = False
            else:
                chosen.append(idx)
        return locs[keep]

    return nms(max_locs, max_vals, True), nms(min_locs, min_vals, False)


def fenshuiling_boundry(surface_data: np.ndarray, max_locs: np.ndarray, yuzhi: float):
    markers = np.zeros(surface_data.shape, dtype=np.int32)
    for k, (r, c) in enumerate(max_locs, start=1):
        if 0 <= r < markers.shape[0] and 0 <= c < markers.shape[1]:
            markers[r, c] = k

    smoothed = filters.gaussian(surface_data, sigma=1.5, preserve_range=True)
    gx = filters.sobel_h(smoothed)
    gy = filters.sobel_v(smoothed)
    gradient_mag = np.hypot(gx, gy)
    local_mean = ndimage.uniform_filter(surface_data, size=5)
    local_mean2 = ndimage.uniform_filter(surface_data**2, size=5)
    local_contrast = np.sqrt(np.maximum(local_mean2 - local_mean**2, 0))
    gradient_mag[gradient_mag < 0.01 * local_contrast] = 255

    if max_locs.size:
        distance = ndimage.distance_transform_edt(markers == 0)
        background = distance > yuzhi * distance.max()
        markers[background] = 255
    labels = segmentation.watershed(gradient_mag, markers=markers, watershed_line=True)

    boundary_coords = []
    for r, c in max_locs:
        if r >= labels.shape[0] or c >= labels.shape[1]:
            boundary_coords.append(np.empty((0, 3)))
            continue
        region_mask = labels == labels[r, c]
        contours = measure.find_contours(region_mask.astype(float), 0.5)
        if not contours:
            boundary_coords.append(np.empty((0, 3)))
            continue
        coords_rc = contours[0]
        rows = np.clip(np.rint(coords_rc[:, 0]).astype(int), 0, surface_data.shape[0] - 1)
        cols = np.clip(np.rint(coords_rc[:, 1]).astype(int), 0, surface_data.shape[1] - 1)
        boundary_coords.append(np.column_stack([cols, rows, surface_data[rows, cols]]))
    return labels == 0, boundary_coords


def fushikengtiqu(data: np.ndarray, pits: list[np.ndarray], max_loc: np.ndarray):
    num_pits = len(pits)
    depth = np.zeros(num_pits)
    sjb = np.zeros(num_pits)
    zhijin = np.zeros(num_pits)
    ref = data.min()
    for k in range(num_pits):
        if k >= len(max_loc) or pits[k].size == 0:
            continue
        r, c = max_loc[k]
        depth[k] = data[r, c] - ref + 1
        bx = np.ptp(pits[k][:, 0]) + 1
        by = np.ptp(pits[k][:, 1]) + 1
        zhijin[k] = (bx + by) * 0.5
        sjb[k] = depth[k] / max(zhijin[k], np.finfo(float).eps)
    valid = depth > 0
    return depth[valid], sjb[valid], zhijin[valid]


def jixiantiqu_3d(surface_data: np.ndarray, n: int, params: Optional[dict] = None, yuzhi: float = 0.3):
    max_locs, min_locs = find_local_extrema(surface_data, params)
    boundaries, boundary_coords = fenshuiling_boundry(surface_data, max_locs, yuzhi)
    shengdu, sjb, zhijin = fushikengtiqu(surface_data, boundary_coords, max_locs)
    return shengdu, sjb, zhijin, max_locs, min_locs, boundaries, boundary_coords


def fangsuo(a: np.ndarray, new_w: int, new_l: int, new_n: int) -> np.ndarray:
    return transform.resize(a, (new_w, new_l, new_n), order=0, preserve_range=True, anti_aliasing=False).astype(a.dtype)


def kuaipingjun_from_a(a: np.ndarray, scale: int = 4) -> np.ndarray:
    h = depth_map_from_a(a)
    return block_average(h, scale)


def block_average(baseline: np.ndarray, scale: int = 4) -> np.ndarray:
    w = baseline.shape[0] // scale
    l = baseline.shape[1] // scale
    trimmed = baseline[: w * scale, : l * scale]
    down = trimmed.reshape(w, scale, l, scale).mean(axis=(1, 3))
    return (down - 3) * 0.025


def fenbujianyan(x: np.ndarray):
    x = np.asarray(x, dtype=float)
    return {
        "mean": float(np.mean(x)),
        "std": float(np.std(x, ddof=1)) if x.size > 1 else 0.0,
        "normaltest": stats.normaltest(x) if x.size >= 8 else None,
    }


def plot_distribution_check(data: np.ndarray, bin_width: float = 0.1):
    import matplotlib.pyplot as plt

    data = np.asarray(data, dtype=float)
    mu, sigma = stats.norm.fit(data)
    fig1, ax1 = plt.subplots()
    bins = max(1, int(np.ceil((data.max() - data.min()) / bin_width)))
    ax1.hist(data, bins=bins, density=True, color=(0.5, 0.8, 1.0), edgecolor="black")
    x = np.linspace(data.min(), data.max(), 1000)
    ax1.plot(x, stats.norm.pdf(x, mu, sigma), "r-", linewidth=2)
    ax1.set_xlabel("数据值")
    ax1.set_ylabel("概率密度")
    ax1.set_title("数据直方图与拟合曲线")
    ax1.legend(["拟合正态曲线", "数据分布"])

    fig2 = plt.figure()
    stats.probplot(data, dist="norm", plot=plt)
    plt.title("Q-Q图检验正态性")
    return {"mu": mu, "sigma": sigma, "hist_figure": fig1, "qq_figure": fig2}


def shujuxiugai(
    a: np.ndarray,
    target_min: float,
    delta: float = 1,
    max_extra: float = 1,
    sigma: float = 0.5,
    levels: int = 3,
    intensity: Optional[Iterable[float]] = None,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    rng = rng or _as_rng()
    a = np.asarray(a, dtype=float)
    if intensity is None:
        intensity = [1.2, 1.0, 0.8]
    intensity = np.asarray(list(intensity), dtype=float)
    if len(intensity) != levels:
        raise ValueError("intensity 长度必须与 levels 一致")

    mask = a <= target_min + delta
    original_min = a.min()
    depth_range = target_min + delta - original_min
    layer_edges = np.linspace(original_min, target_min + delta, levels + 1)
    base_increment = np.maximum(0, target_min - a)
    filtered_rand = filters.gaussian(rng.random(a.shape), sigma=sigma, preserve_range=True)
    layer_weights = np.zeros((levels, *a.shape), dtype=float)
    for i in range(levels):
        lower = layer_edges[i] - depth_range / (2 * levels)
        upper = layer_edges[i + 1] + depth_range / (2 * levels)
        denom = max(upper - lower, np.finfo(float).eps)
        layer_weights[i] = 1 / (1 + np.exp(10 * (a - (lower + upper) / 2) / denom))
    layer_weights /= np.maximum(layer_weights.sum(axis=0, keepdims=True), np.finfo(float).eps)

    extra = np.zeros_like(a)
    for i in range(levels):
        extra += filtered_rand * max_extra * intensity[i] * layer_weights[i]
    b = np.rint(a + base_increment + extra * mask)
    b[b < target_min] = target_min
    return b


def power_fit(t_data: np.ndarray, y_data: np.ndarray):
    def model(t, a, n):
        return a * t**n

    coeffs, _ = curve_fit(model, t_data, y_data, p0=[1, 1], maxfev=10000)
    residuals = y_data - model(t_data, *coeffs)
    r2 = 1 - np.sum(residuals**2) / np.sum((y_data - y_data.mean()) ** 2)
    return coeffs[0], coeffs[1], r2


def ca(
    xy: np.ndarray,
    f: int,
    a: np.ndarray,
    data: np.ndarray,
    data_x: float,
    n: int,
    w: int,
    l: int,
    space: float,
    d: np.ndarray,
    stage_number: int,
    cl: np.ndarray,
    rng: Optional[np.random.Generator] = None,
):
    rng = rng or _as_rng()
    (
        p_uniform_base,
        p_passive_base,
        p_break,
        cl_threshold,
        alpha_corrosion,
        simutive_point,
        alpha_p_break,
        p_h,
        p_v,
        p_o,
    ) = xy
    alpha_passive = 0.8

    flat_size = w * l * n
    count = int(round(flat_size * simutive_point))
    if count > 0:
        idx = rng.integers(0, flat_size, size=count)
        sub = np.unravel_index(idx, (w, l, n))
        d[sub[0], sub[1], sub[2] + 1] = 1

    k0 = 0
    beta = 1
    average_depth = 0.0

    for k in range(1, f + 1):
        convex_points, p_tuwei = tuweipolie(a, w, l, p_o, 30, n)
        convex_set = set(map(tuple, convex_points.tolist()))
        boundary = detect_boundry_3d(a, n)
        if boundary.size:
            bx, by, bz = boundary[:, 0], boundary[:, 1], boundary[:, 2]
            a_vals = a[bx, by, bz]
            valid = a_vals != 0
            boundary = boundary[valid]
            bx, by, bz = boundary[:, 0], boundary[:, 1], boundary[:, 2]
            a_vals = a[bx, by, bz]
            d_vals = d[bx, by, bz]
            cl_vals = cl[bx, by]
            cl_factor = cl_vals / cl_threshold
            decay = 1 + (beta - 1) * (k0 - k + 1) / k0 if k <= k0 and k0 else 1
            p_uniform = p_uniform_base * (1 + alpha_corrosion * cl_factor) * decay
            p_passive = p_passive_base * (1 - alpha_passive * cl_factor)
            rand_vals = rng.random(a_vals.shape)

            metal = a_vals == 1
            corrode = metal & (rand_vals < p_uniform)
            d_mask = corrode & (d_vals > 1)
            a_mask = corrode & (d_vals == 1)
            d[bx[d_mask], by[d_mask], bz[d_mask]] -= 1
            a[bx[a_mask], by[a_mask], bz[a_mask]] = 0

            passive = metal & ~corrode & (rand_vals < p_passive)
            a[bx[passive], by[passive], bz[passive]] = 2

            passive_break = (a_vals == 2) & (d_vals == 1)
            p_break_cl = np.zeros_like(a_vals, dtype=float)
            valid_idx = np.where(passive_break)[0]
            if valid_idx.size:
                temp = p_break * (1 + alpha_p_break * cl_factor[valid_idx])
                if stage_number == 1:
                    temp = temp**2 / max(p_break, np.finfo(float).eps)
                for j, idx in enumerate(valid_idx):
                    if (int(bx[idx]), int(by[idx])) in convex_set:
                        temp[j] *= p_tuwei
                p_break_cl[valid_idx] = temp

            break_mask = passive_break & (rng.random(a_vals.shape) < p_break_cl)
            if np.any(break_mask):
                a[bx[break_mask], by[break_mask], bz[break_mask]] = 0
                cl[bx[break_mask], by[break_mask]] = np.minimum(cl[bx[break_mask], by[break_mask]] + 1, cl_threshold)
                for x, y, z in boundary[break_mask]:
                    a, cl = spread_corrosion2(int(x), int(y), int(z), a, p_h, p_v, n, cl, cl_threshold, rng)
            cl[cl >= cl_threshold] = 0

        quality_loss = (w * l * n - np.sum(a == 1)) / (w * l * n)
        average_depth = quality_loss * n * space
        if data_x - average_depth <= 0:
            break

    baseline, _, _, depth_map = moving_avg_3d(a, 11, w, l, n)
    baseline = expand_matrix(baseline, 1)
    jicha = baseline.max() - baseline.min()
    bj_depth = np.mean(depth_map - depth_map.min()) * space
    if jicha < 3:
        yuzhi, scale = 0.3, 15
    elif jicha < 5:
        yuzhi, scale = 0.4, 20
    else:
        yuzhi, scale = 0.5, 25
    params = {"MinProminence": 0.05, "MinDistance": 15, "Neighborhood": [scale, scale]}
    shengdu, sjb, *_ = jixiantiqu_3d(baseline, n, params, yuzhi)
    shengdu = np.log(np.maximum(shengdu * space, np.finfo(float).eps))
    sjb = sjb / 10
    jsb = np.log(1 / np.maximum(sjb, np.finfo(float).eps))
    sigma1 = float(np.std(jsb, ddof=1)) if jsb.size > 1 else 0.0
    sigma2 = float(np.std(shengdu, ddof=1)) if shengdu.size > 1 else 0.0
    simulated = np.array([average_depth, bj_depth, np.mean(jsb), np.mean(shengdu), sigma1, sigma2])
    cs = (simulated - data) / data
    return cs, a, d, cl


def fitness(
    xy: np.ndarray,
    nind: int,
    data: np.ndarray,
    data_x: float,
    a_jisuan: np.ndarray,
    f: int,
    n: int,
    w: int,
    l: int,
    space: float,
    d_jisuan: np.ndarray,
    stage_number: int,
    cl_jisuan: np.ndarray,
    seed: Optional[int] = None,
):
    rng = _as_rng(seed)
    sd_objv = np.zeros((nind, len(data)))
    sd_a, sd_d, sd_cl = [], [], []
    for i in range(nind):
        cs, a_out, d_out, cl_out = ca(
            xy[i],
            f,
            a_jisuan.copy(),
            data,
            data_x,
            n,
            w,
            l,
            space,
            d_jisuan.copy(),
            stage_number,
            cl_jisuan.copy(),
            rng,
        )
        sd_objv[i, :] = np.round(np.abs(cs), 2)
        sd_a.append(a_out)
        sd_d.append(d_out)
        sd_cl.append(cl_out)
    return sd_objv, sd_a, sd_d, sd_cl


def ga(
    w: int,
    l: int,
    n: int,
    data_x: float,
    data: np.ndarray,
    a_input: Optional[np.ndarray],
    f: int,
    stage_number: int,
    space: float,
    d_input: Optional[np.ndarray],
    cl_input: Optional[np.ndarray],
    nind: int = 300,
    maxgen: int = 100,
    seed: Optional[int] = None,
):
    rng = _as_rng(seed)
    lind = 10
    bits_per_param = 11
    lb = np.array([0, 0, 0, 5, 1, 0, 1, 0, 0, 1], dtype=float)
    ub = np.array([0.3, 1, 0.005, 35, 35, 0.1, 35, 0.5, 0.5, 15], dtype=float)
    slind = 10
    base_px = 0.5
    base_pm = 0.5
    decay_rate = 0.2
    sigma_share = 0.3
    chrom = latin_begin(nind, lind, bits_per_param, rng)

    perfect_result = perfect_parameter = perfect_a = perfect_d = perfect_cl = None
    for gen in range(1, maxgen):
        xy = er2shi(chrom, lb, ub, bits_per_param)
        current_px = max(0.6, min(0.95, base_px * np.exp(-decay_rate * (gen / maxgen))))
        current_pm = max(0.01, min(0.3, base_pm + (0.3 - base_pm) * (gen / maxgen)))

        if stage_number == 1:
            a0 = np.ones((w, l, n + 1), dtype=np.int8)
            a0[:, :, 0] = 0
            d0 = np.ones_like(a0, dtype=np.int8) * 3
            cl0 = np.zeros((w, l), dtype=float)
        else:
            a0, d0, cl0 = a_input, d_input, cl_input

        objv, sd_a, sd_d, sd_cl = fitness(xy, nind, data, data_x, a0, f, n, w, l, space, d0, stage_number, cl0, seed)
        objv = np.delete(objv, 4, axis=1)
        objv[:, 3] = 0.6 * objv[:, 3] + 0.4 * objv[:, 4]
        objv = np.delete(objv, 4, axis=1)
        obj_score = 0.1 * objv[:, 0] + 0.3 * objv[:, 1] + 0.2 * objv[:, 2] + 0.4 * objv[:, 3]
        fit = 1 / (obj_score + np.finfo(float).eps)
        dist_matrix = cdist(xy, xy)
        share_terms = np.maximum(1 - dist_matrix / sigma_share, 0)
        fit = fit / (share_terms.sum(axis=1) + 1)

        best_idx = int(np.argmin(obj_score))
        if perfect_result is None or perfect_result.sum() > objv[best_idx].sum():
            perfect_result = objv[best_idx].copy()
            perfect_parameter = xy[best_idx].copy()
            perfect_a = sd_a[best_idx]
            perfect_d = sd_d[best_idx]
            perfect_cl = sd_cl[best_idx]
        if perfect_result.sum() <= 0.01:
            break

        worst = np.argsort(fit)[:slind]
        diversity = np.std(fit)
        tournament_size = max(2, round(5 * diversity))
        selected = tournament_selection(fit, slind, tournament_size, rng)
        children = mut(jiaocha(chrom[selected, :], current_px, lind, rng), current_pm, rng)
        chrom[worst, :] = children

    return perfect_result, perfect_parameter, perfect_a, perfect_d, perfect_cl


def split_uniform_blocks(w: int, l: int, num_blocks: int = 5) -> np.ndarray:
    edges = np.linspace(0, w, num_blocks + 1).round().astype(int)
    return np.array([[edges[i], edges[i + 1], 0, l] for i in range(num_blocks)], dtype=int)


def block_process(
    block: Block,
    k: int,
    n: int,
    p_uniform_base: float,
    p_passive_base: float,
    p_break: float,
    cl_threshold: float,
    alpha_corrosion: float,
    alpha_passive: float,
    alpha_p_break: float,
    p_h: float,
    p_v: float,
    p_o: float,
    k0: int,
    beta: float,
    stage_number: int,
    rng: Optional[np.random.Generator] = None,
    use_taichi: bool = False,
) -> Block:
    rng = rng or _as_rng()
    a, d, cl = block.a, block.d, block.cl
    wb, lb = a.shape[:2]
    boundary = detect_boundry_3d(a, n)
    if boundary.size == 0:
        return block
    if use_taichi and boundary_update_taichi is not None:
        decay = 1 + (beta - 1) * (k0 - k + 1) / k0 if k <= k0 and k0 else 1
        a, d, cl, break_points = boundary_update_taichi(
            boundary,
            a,
            d,
            cl,
            p_uniform_base,
            p_passive_base,
            p_break,
            cl_threshold,
            alpha_corrosion,
            alpha_passive,
            alpha_p_break,
            stage_number,
            decay,
            rng,
        )
        if break_points.size:
            for x, y, z in break_points:
                a, cl = spread_corrosion2(int(x), int(y), int(z), a, p_h, p_v, n, cl, cl_threshold, rng)
        cl[cl >= cl_threshold] = 0
        return Block(a=a, d=d, cl=cl)
    bx, by, bz = boundary[:, 0], boundary[:, 1], boundary[:, 2]
    a_vals = a[bx, by, bz]
    valid = a_vals != 0
    boundary = boundary[valid]
    bx, by, bz = boundary[:, 0], boundary[:, 1], boundary[:, 2]
    a_vals = a[bx, by, bz]
    d_vals = d[bx, by, bz]
    cl_factor = cl[bx, by] / cl_threshold
    decay = 1 + (beta - 1) * (k0 - k + 1) / k0 if k <= k0 and k0 else 1
    p_uniform = p_uniform_base * (1 + alpha_corrosion * cl_factor) * decay
    p_passive = p_passive_base * (1 - alpha_passive * cl_factor)
    rand_vals = rng.random(a_vals.shape)
    metal = a_vals == 1
    corrode = metal & (rand_vals < p_uniform)
    d_mask = corrode & (d_vals > 1)
    a_mask = corrode & (d_vals == 1)
    d[bx[d_mask], by[d_mask], bz[d_mask]] -= 1
    a[bx[a_mask], by[a_mask], bz[a_mask]] = 0
    passive = metal & ~corrode & (rand_vals < p_passive)
    a[bx[passive], by[passive], bz[passive]] = 2
    passive_break = (a_vals == 2) & (d_vals == 1)
    p_break_cl = np.zeros_like(a_vals, dtype=float)
    valid_idx = np.where(passive_break)[0]
    if valid_idx.size:
        cf = cl_factor[valid_idx]
        p_break_cl[valid_idx] = p_break * (1 + alpha_p_break * cf) ** (2 if stage_number == 1 else 1)
    break_mask = passive_break & (rng.random(a_vals.shape) < p_break_cl)
    if np.any(break_mask):
        a[bx[break_mask], by[break_mask], bz[break_mask]] = 0
        cl[bx[break_mask], by[break_mask]] = np.minimum(cl[bx[break_mask], by[break_mask]] + 1, cl_threshold)
        for x, y, z in boundary[break_mask]:
            a, cl = spread_corrosion2(int(x), int(y), int(z), a, p_h, p_v, n, cl, cl_threshold, rng)
    cl[cl >= cl_threshold] = 0
    return Block(a=a, d=d, cl=cl)

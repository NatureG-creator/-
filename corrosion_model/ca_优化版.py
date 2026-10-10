"""Cellular automaton corrosion evolution converted from MATLAB `CA.m`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy import ndimage

from .matlab_compat import matlab_round, sub2ind_matlab, take_matlab_linear, put_matlab_linear
from .progress import ProgressTarget, emit_progress, should_report
from .taichi_accel_优化版 import (
    TaichiCAState, boundary_update_taichi, detect_boundary_taichi, taichi_available,
)
from unified_config import (
    CA_CONFIG,
    MATLAB_CA_COMPARISON_CONFIG,
    POSTPROCESS_CONFIG,
    matlab_ca_postprocess_settings,
)

_BASIC_OFFSETS = np.array(
    [
        [0, -1, 0],
        [0, 1, 0],
        [-1, 0, 0],
        [1, 0, 0],
        [0, 0, -1],
        [0, 0, 1],
    ],
    dtype=np.int8,
)
_SPREAD_MESH = np.array(
    np.meshgrid([-1, 0, 1], [-1, 0, 1], [-1, 0, 1], indexing="xy")
)
_SPREAD_OFFSETS = np.delete(_SPREAD_MESH.reshape(3, -1).T, 13, axis=0).astype(np.int8)
_SPREAD_PROB_FACTORS = np.empty(_SPREAD_OFFSETS.shape[0], dtype=np.float64)
for _idx, _offset in enumerate(_SPREAD_OFFSETS):
    _dist = float(np.linalg.norm(_offset))
    if np.isclose(_dist, 1.0):
        _SPREAD_PROB_FACTORS[_idx] = 1.0
    elif np.isclose(_dist, np.sqrt(2.0)):
        _SPREAD_PROB_FACTORS[_idx] = 0.6
    else:
        _SPREAD_PROB_FACTORS[_idx] = 0.3


@dataclass
class CAResult:
    """Return object matching MATLAB `[CS, a, d, CL_concentration]`."""

    cs: np.ndarray
    a: np.ndarray
    d: np.ndarray
    cl_concentration: np.ndarray
    iterations: int
    average_depth: float


def detect_boundary_3d(a: np.ndarray, n: int) -> np.ndarray:
    """Python version of `detect_boundry_3D.m`.

    Returns MATLAB-style 1-based coordinates `[x, y, z]`. Internally NumPy
    arrays are 0-based, so every returned coordinate is shifted by `+1`.

    可调项：`a`、`n`。
    """
    a = np.asarray(a)
    if a.ndim != 3:
        raise ValueError("输入 a 必须是三维数组")
    if n < 1:
        raise ValueError("n 必须是正数")
    if not np.any(a == 0):
        return np.empty((0, 3), dtype=np.int64)

    zero_mask = a == 0
    z_has_zero = np.any(zero_mask, axis=(0, 1))
    z_nonzero = np.flatnonzero(z_has_zero)
    if z_nonzero.size == 0:
        return np.empty((0, 3), dtype=np.int64)
    # MATLAB `find(..., 1, 'last')` 返回 1-based；Python 已是 0-based。
    jizhun_z_0based = min(z_nonzero[-1] + 1, n)
    process_depth = min(jizhun_z_0based + 1, a.shape[2])

    a_process = a[:, :, :process_depth]
    non_zero_mask = a_process != 0
    zero_mask_process = ~non_zero_mask

    structure = np.zeros((3, 3, 3), dtype=bool)
    structure[1, 1, 0] = True
    structure[1, 1, 2] = True
    structure[1, 0, 1] = True
    structure[1, 2, 1] = True
    structure[0, 1, 1] = True
    structure[2, 1, 1] = True
    expanded_zero = ndimage.binary_dilation(
        zero_mask_process, structure=structure, border_value=0
    )
    boundary_mask = non_zero_mask & expanded_zero
    coords_0based = np.argwhere(boundary_mask)
    # 索引改动：Python `argwhere` 返回 0-based，MATLAB 边界矩阵使用 1-based。
    return coords_0based.astype(np.int64) + 1


def convex_rupture_points(
    a: np.ndarray, w: int, l: int, p_o: float, max_gaocha: float, n: int
) -> tuple[np.ndarray, float]:
    """Python version of `tuweipolie.m`.

    可调项：`a`、`w`、`l`、`p_o`、`max_gaocha`、`n`。
    """
    depth_map = first_metal_depth(a, w, l, n)
    gaocha = float(np.max(depth_map) - np.min(depth_map))
    if gaocha >= 2:
        threshold = 0.05 * gaocha + float(np.min(depth_map))
        convex_mask = depth_map >= threshold
        rows, cols = np.nonzero(convex_mask)
        points = np.column_stack([rows + 1, cols + 1]).astype(np.int64)
        if gaocha <= max_gaocha:
            p_xiugai = (gaocha / max_gaocha) * (p_o - 1.0) + 1.0
        else:
            p_xiugai = p_o
        return points, float(p_xiugai)
    return np.empty((0, 2), dtype=np.int64), 1.0


def first_metal_depth(a: np.ndarray, w: int, l: int, n: int) -> np.ndarray:
    """Find first `a==1` layer like MATLAB `find(..., 1, 'first')`.

    可调项：`a`、`w`、`l`、`n`。
    """
    metal_mask = a[:, :, :n] == 1
    has_metal = np.any(metal_mask, axis=2)
    first_idx = np.argmax(metal_mask, axis=2) + 1
    depth_map = np.where(has_metal, first_idx, n + 1).astype(np.float64)
    return depth_map


def _spread_corrosion_basic(
    x: int,
    y: int,
    z: int,
    a: np.ndarray,
    p_h: float,
    p_v: float,
    n: int,
    cl_concentration: np.ndarray,
    cl_threshold: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Nested MATLAB `spread_corrosion` helper from `spread_corrosion2.m`."""
    w, l, _ = a.shape
    for dx, dy, dz in _BASIC_OFFSETS:
        ni = x + int(dx)
        nj = y + int(dy)
        nk = z + int(dz)
        if (1 <= ni <= w) and (1 <= nj <= l) and (1 <= nk <= n):
            # 索引改动：MATLAB `(ni,nj,nk)` -> Python `[ni-1,nj-1,nk-1]`。
            ii, jj, kk = ni - 1, nj - 1, nk - 1
            base_prob = p_h if dz == 0 else p_v
            cl_factor = cl_concentration[ii, jj] / cl_threshold
            prob = base_prob * 0.5 * (1.0 + cl_factor)
            if rng.random() < prob and a[ii, jj, kk] == 1:
                a[ii, jj, kk] = 0
    return a, cl_concentration


def spread_corrosion2(
    x: int,
    y: int,
    z: int,
    a: np.ndarray,
    p_h: float,
    p_v: float,
    n: int,
    cl_concentration: np.ndarray,
    cl_threshold: float,
    rng: np.random.Generator | None = None,
    *,
    inplace: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Python version of MATLAB `spread_corrosion2.m`.

    可调项：`x`、`y`、`z`、`a`、`p_h`、`p_v`、`n`、
    `cl_concentration`、`cl_threshold`、`rng`。

    Input coordinates are MATLAB 1-based. Returned arrays are copies, matching
    MATLAB pass-by-value behavior from the caller's point of view.
    """
    rng = np.random.default_rng() if rng is None else rng
    # 公共函数默认仍按 MATLAB 值传递复制；CA 内部独占状态时允许原地更新。
    if not inplace:
        a = np.array(a, copy=True)
        cl_concentration = np.array(cl_concentration, copy=True)
    max_prob = max(p_h, p_v)
    base_probs = _SPREAD_PROB_FACTORS * max_prob

    w, l, _ = a.shape
    for offset, base_prob in zip(_SPREAD_OFFSETS, base_probs):
        ni = x + int(offset[0])
        nj = y + int(offset[1])
        nk = z + int(offset[2])
        if (1 <= ni <= w) and (1 <= nj <= l) and (1 <= nk <= n):
            ii, jj, kk = ni - 1, nj - 1, nk - 1
            cl_factor = (cl_concentration[ii, jj] / cl_threshold) ** 2
            prob = base_prob * (1.0 + cl_factor)
            if rng.random() < prob and a[ii, jj, kk] == 1:
                a[ii, jj, kk] = 0
                cl_concentration[ii, jj] = min(
                    cl_concentration[ii, jj] + 1.0, cl_threshold
                )
                if rng.random() < 0.8:
                    a, cl_concentration = _spread_corrosion_basic(
                        ni,
                        nj,
                        nk,
                        a,
                        p_h,
                        p_v,
                        n,
                        cl_concentration,
                        cl_threshold,
                        rng,
                    )
    return a, cl_concentration


def initialise_stage(
    w: int,
    l: int,
    n: int,
    sensitive_point: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Initialise `a`, `d`, and chloride concentration like `GA.m`/`CA.m`.

    可调项：`w`、`l`、`n`、`sensitive_point`、`rng`。
    """
    a = np.ones((w, l, n + 1), dtype=np.float64)
    a[:, :, 0] = 0
    d = np.ones_like(a) * float(CA_CONFIG["initial_d"])
    count = int(matlab_round(w * l * n * sensitive_point))
    if count > 0:
        # MATLAB `randi(w*l*n,1,count)` samples with replacement, 1-based.
        picks = rng.integers(1, w * l * n + 1, size=count)
        flat = np.ravel(d, order="F")
        flat[picks - 1] = 1.0
    cl = np.full((w, l), float(CA_CONFIG["initial_cl"]), dtype=np.float64)
    return a, d, cl


def run_ca(
    xy: np.ndarray,
    F: int,
    a: np.ndarray | None,
    data: np.ndarray,
    data_x: float,
    n: int,
    w: int,
    l: int,
    space: float,
    d: np.ndarray | None,
    stage_number: int,
    cl_concentration: np.ndarray | None,
    rng: np.random.Generator | None = None,
    use_taichi: bool = False,
    verbose: ProgressTarget = False,
    progress_label: str = "CA",
) -> CAResult:
    """Python version of MATLAB `CA.m`.

    可调项：`xy`、`F`、`a`、`data`、`data_x`、`n`、`w`、`l`、`space`、
    `d`、`stage_number`、`cl_concentration`、`rng`、`use_taichi`。

    The update order follows the MATLAB script: boundary detection, corrosion,
    passivation, passive-film rupture, chloride reset, then depth stop check.
    """
    from .analysis_优化版 import (
        expand_matrix,
        jixiantiqu_3d,
        moving_avg_3d,
        normfit_sigma,
        safe_log,
    )

    rng = np.random.default_rng() if rng is None else rng
    xy = np.asarray(xy, dtype=np.float64)
    data = np.asarray(data, dtype=np.float64)
    p_uniform_base = xy[0]
    p_passive_base = xy[1]
    p_break = xy[2]
    cl_threshold = xy[3]
    alpha_corrosion = xy[4]
    alpha_passive = float(CA_CONFIG["alpha_passive"])
    sensitive_point = xy[5]
    alpha_p_break = xy[6]
    p_h = xy[7]
    p_v = xy[8]
    p_o = xy[9]
    taichi_ok = use_taichi and taichi_available()
    if a is None or d is None or cl_concentration is None:
        a, d, cl_concentration = initialise_stage(w, l, n, sensitive_point, rng)
    else:
        a = np.array(a, copy=True, dtype=np.float64)
        d = np.array(d, copy=True, dtype=np.float64)
        cl_concentration = np.array(cl_concentration, copy=True, dtype=np.float64)
        count = int(matlab_round(w * l * n * sensitive_point))
        if count > 0:
            picks = rng.integers(1, w * l * n + 1, size=count)
            flat = np.ravel(d, order="F")
            flat[picks - 1] = 1.0

    # 初始化/敏感点随机抽样结束后才转换，保持原有随机流与初始化语义。
    if taichi_ok:
        fast_state = TaichiCAState.from_arrays(a, d, cl_concentration)
        a, d, cl_concentration = fast_state.a, fast_state.d, fast_state.cl

    k_completed = 0
    average_depth = 0.0
    k0 = int(CA_CONFIG["initial_enhancement_steps"])
    beta = float(CA_CONFIG["initial_enhancement_beta"])
    emit_progress(verbose, f"[{progress_label}] 开始：F={F}, 网格={w}x{l}x{n}, Taichi={taichi_ok}")
    for k in range(1, F + 1):
        k_completed = k
        convex_points, p_tuwei = convex_rupture_points(
            a,
            w,
            l,
            p_o,
            float(CA_CONFIG["convex_height_limit"]),
            n,
        )
        if taichi_ok:
            boundary = detect_boundary_taichi(a, n)
        else:
            boundary = detect_boundary_3d(a, n)
        boundary_count = int(boundary.shape[0]) if boundary.size != 0 else 0
        if boundary.size != 0:
            convex_mask = None
            if convex_points.size != 0:
                convex_mask = np.zeros((w, l), dtype=bool)
                convex_mask[convex_points[:, 0] - 1, convex_points[:, 1] - 1] = True

            if taichi_ok:
                boundary_idx = sub2ind_matlab(a.shape, boundary)
                a_vals = take_matlab_linear(a, boundary_idx)
                valid_mask = a_vals != 0
                boundary = boundary[valid_mask, :]
                if boundary.size != 0:
                    boundary_zero = boundary.astype(np.int32) - 1
                    if convex_mask is not None:
                        convex_flags = convex_mask[boundary[:, 0] - 1, boundary[:, 1] - 1].astype(
                            np.int32
                        )
                    else:
                        convex_flags = np.zeros(boundary.shape[0], dtype=np.int32)
                    decay_scalar = 1.0
                    if k <= k0 and k0 != 0:
                        decay_scalar = 1.0 + (beta - 1.0) * (k0 - k + 1.0) / k0
                    a, d, cl_concentration, break_points = boundary_update_taichi(
                        boundary_zero,
                        convex_flags,
                        a,
                        d,
                        cl_concentration,
                        p_uniform_base,
                        p_passive_base,
                        p_break,
                        cl_threshold,
                        alpha_corrosion,
                        alpha_passive,
                        alpha_p_break,
                        stage_number,
                        decay_scalar,
                        p_tuwei,
                        rng,
                    )
                    if break_points.size != 0:
                        for x0, y0, z0 in break_points:
                            a, cl_concentration = spread_corrosion2(
                                int(x0) + 1,
                                int(y0) + 1,
                                int(z0) + 1,
                                a,
                                p_h,
                                p_v,
                                n,
                                cl_concentration,
                                cl_threshold,
                                rng,
                                inplace=True,
                            )
                    cl_concentration[cl_concentration >= cl_threshold] = 0
            else:
                boundary_idx = sub2ind_matlab(a.shape, boundary)
                boundary_xy_idx = sub2ind_matlab(cl_concentration.shape, boundary[:, :2])
                a_vals = take_matlab_linear(a, boundary_idx)
                valid_mask = a_vals != 0
                boundary_idx = boundary_idx[valid_mask]
                boundary_xy_idx = boundary_xy_idx[valid_mask]
                boundary = boundary[valid_mask, :]
                a_vals = a_vals[valid_mask]
                d_vals = take_matlab_linear(d, boundary_idx)
                cl_vals = take_matlab_linear(cl_concentration, boundary_xy_idx)
                cl_factor = cl_vals / cl_threshold
                decay_factor = np.ones_like(a_vals, dtype=np.float64)
                if k <= k0 and k0 != 0:
                    decay_factor = 1.0 + (beta - 1.0) * (k0 - k + 1.0) / k0
                p_uniform = p_uniform_base * (1.0 + alpha_corrosion * cl_factor) * decay_factor
                p_passive = p_passive_base * (1.0 - alpha_passive * cl_factor)
                rand_vals = rng.random(a_vals.shape)

                metal_mask = a_vals == 1
                corrode_mask = metal_mask & (rand_vals < p_uniform)
                d_corrode_mask = corrode_mask & (d_vals > 1)
                a_corrode_mask = corrode_mask & (d_vals == 1)
                if np.any(d_corrode_mask):
                    old_d = take_matlab_linear(d, boundary_idx[d_corrode_mask])
                    put_matlab_linear(d, boundary_idx[d_corrode_mask], old_d - 1)
                if np.any(a_corrode_mask):
                    put_matlab_linear(a, boundary_idx[a_corrode_mask], 0.0)
                passive_mask = metal_mask & ~corrode_mask & (rand_vals < p_passive)
                if np.any(passive_mask):
                    put_matlab_linear(a, boundary_idx[passive_mask], 2.0)

                passive_break_mask = (a_vals == 2) & (d_vals == 1)
                p_break_cl = np.zeros_like(a_vals, dtype=np.float64)
                valid_idx = np.flatnonzero(passive_break_mask)
                if valid_idx.size != 0:
                    valid_factor = cl_factor[valid_idx]
                    if stage_number == 1:
                        temp_p = p_break * (1.0 + alpha_p_break * valid_factor) ** 2
                    else:
                        temp_p = p_break * (1.0 + alpha_p_break * valid_factor)
                    boundary_xy = boundary[passive_break_mask, :2]
                    if convex_mask is not None and boundary_xy.size != 0:
                        is_convex = convex_mask[boundary_xy[:, 0] - 1, boundary_xy[:, 1] - 1]
                        temp_p[is_convex] = temp_p[is_convex] * p_tuwei
                    p_break_cl[valid_idx] = temp_p
                break_mask = passive_break_mask & (rng.random(passive_break_mask.shape) < p_break_cl)
                if np.any(break_mask):
                    put_matlab_linear(a, boundary_idx[break_mask], 0.0)
                    old_cl = take_matlab_linear(cl_concentration, boundary_xy_idx[break_mask])
                    put_matlab_linear(
                        cl_concentration,
                        boundary_xy_idx[break_mask],
                        np.minimum(old_cl + 1.0, cl_threshold),
                    )
                    for idx in np.flatnonzero(break_mask):
                        a, cl_concentration = spread_corrosion2(
                            int(boundary[idx, 0]),
                            int(boundary[idx, 1]),
                            int(boundary[idx, 2]),
                            a,
                            p_h,
                            p_v,
                            n,
                            cl_concentration,
                            cl_threshold,
                            rng,
                            inplace=True,
                        )
                cl_concentration[cl_concentration >= cl_threshold] = 0

        quality_loss = (w * l * n - np.sum(a == 1)) / (w * l * n)
        average_depth = float(quality_loss * n * space)
        if verbose and should_report(k, F):
            emit_progress(
                verbose,
                (
                    f"[{progress_label}] 迭代 {k}/{F} | "
                    f"边界元胞={boundary_count} | 平均腐蚀深度={average_depth:.4f}"
                ),
            )
        if data_x - average_depth <= 0:
            emit_progress(
                verbose,
                f"[{progress_label}] 提前停止：{k}/{F} 已达到目标平均腐蚀深度 {data_x}",
            )
            break

    size_chuangkou = int(POSTPROCESS_CONFIG["auto_plot_window_size"])
    baseline, _, _, depth_map = moving_avg_3d(a, size_chuangkou, w, l, n)
    baseline = expand_matrix(baseline, 1)
    jicha = float(np.max(baseline) - np.min(baseline))
    bj_depth = float(np.mean(depth_map - np.min(depth_map)) * space)
    yuzhi, scale = matlab_ca_postprocess_settings(jicha)
    params = {
        "MinProminence": float(MATLAB_CA_COMPARISON_CONFIG["min_prominence"]),
        "MinDistance": int(MATLAB_CA_COMPARISON_CONFIG["min_distance"]),
        "Neighborhood": (scale, scale),
    }
    shengdu, sjb, *_ = jixiantiqu_3d(baseline, n, params, yuzhi)
    shengdu_log = safe_log(shengdu * space, fallback=1.0)
    # MATLAB CA.m 明确使用 `sjb = sjb ./ 10`，不能用物理元胞尺寸比替代。
    sjb_matlab = sjb / float(MATLAB_CA_COMPARISON_CONFIG["sjb_divisor"])
    jsb = safe_log(1.0 / np.maximum(sjb_matlab, 1e-12), fallback=1.0)
    sigma1 = normfit_sigma(jsb)
    sigma2 = normfit_sigma(shengdu_log)
    metrics = np.array(
        [
            average_depth,
            bj_depth,
            float(np.mean(jsb)) if jsb.size else 0.0,
            float(np.mean(shengdu_log)) if shengdu_log.size else 0.0,
            sigma1,
            sigma2,
        ],
        dtype=np.float64,
    )
    data_safe = np.where(data == 0, np.finfo(float).eps, data)
    cs = (metrics - data_safe) / data_safe
    emit_progress(
        verbose,
        f"[{progress_label}] 完成：实际迭代={k_completed}, 平均腐蚀深度={average_depth:.4f}",
    )
    # 输出格式仍与原第二步及后处理一致，a/d 在 CA 结束时恢复 float64。
    return CAResult(cs, a.astype(np.float64, copy=False), d.astype(np.float64, copy=False),
                    cl_concentration, k_completed, average_depth)

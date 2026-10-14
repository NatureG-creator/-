"""Physical surface metrics and bounded-memory NumPy compatibility exports."""

from __future__ import annotations

import os
import uuid
import zipfile
from pathlib import Path

import numpy as np
from .checkpoint import _atomic_replace

METRIC_NAMES = (
    "mean_depth_um", "nonuniform_depth_um", "mu_log_ratio",
    "mu_log_depth", "sigma_log_ratio", "sigma_log_depth",
)
PARAMETER_NAMES = (
    "p_uniform_base", "p_passive_base", "p_break", "cl_threshold",
    "alpha_corrosion", "sensitive_point", "alpha_p_break", "p_h", "p_v", "p_o",
)


def actual_surface_metrics(a: np.ndarray, config: dict) -> tuple[dict, dict]:
    """Use the CA postprocess, exposing undefined fits instead of legacy fallbacks.

    The inherited objective's empty-sample/one-sample fallback remains untouched
    in run_ca. Those fallbacks must not be presented as measured distributions.
    """
    from .strict_ga import scientific_settings
    from .config import source_config
    from corrosion_model.analysis_优化版 import (
        expand_matrix, jixiantiqu_3d, moving_avg_3d, normfit_sigma, safe_log,
    )

    w, l, n = a.shape
    space = float(config["GEOMETRY_CONFIG"]["space_z_um"])
    notes = {}
    with scientific_settings(config):
        baseline, _, _, depth_map = moving_avg_3d(
            a, int(config["POSTPROCESS_CONFIG"]["auto_plot_window_size"]), w, l, n)
        baseline = expand_matrix(baseline, 1)
        jicha = float(np.max(baseline) - np.min(baseline))
        threshold, scale = source_config.matlab_ca_postprocess_settings(jicha)
        params = {"MinProminence": float(config["MATLAB_CA_COMPARISON_CONFIG"]["min_prominence"]),
                  "MinDistance": int(config["MATLAB_CA_COMPARISON_CONFIG"]["min_distance"]),
                  "Neighborhood": (scale, scale)}
        depths, ratios, _, _, _, _, boundaries = jixiantiqu_3d(baseline, n, params, threshold)
        values = {
            "mean_depth_um": float((w * l * n - np.sum(a == 1)) / (w * l * n) * n * space),
            "nonuniform_depth_um": float(np.mean(depth_map - np.min(depth_map)) * space),
            "mu_log_ratio": None, "mu_log_depth": None,
            "sigma_log_ratio": None, "sigma_log_depth": None,
        }
        issue = None
        if depths.size == 0:
            issue = "未提取到有效腐蚀坑，分布参数无法定义；原GA空样本回退仍仅用于原目标计算。"
        elif any(boundary.size == 0 for boundary in boundaries):
            issue = "腐蚀坑边界缺失，原算法填充值不能作为实测分布参数。"
        elif np.any(depths <= 0) or np.any(ratios <= 0):
            issue = "坑深或深宽比存在非正数，无法定义对数分布。"
        if issue is not None:
            notes.update({name: issue for name in METRIC_NAMES[2:]})
        else:
            depth_log = safe_log(depths * space, fallback=1.0)
            ratio_log = safe_log(1.0 / np.maximum(
                ratios / float(config["MATLAB_CA_COMPARISON_CONFIG"]["sjb_divisor"]), 1e-12),
                fallback=1.0)
            values["mu_log_ratio"] = float(np.mean(ratio_log))
            values["mu_log_depth"] = float(np.mean(depth_log))
            if depths.size < 2:
                for name in METRIC_NAMES[4:]:
                    notes[name] = "仅一个有效腐蚀坑，样本标准差（ddof=1）无法定义。"
            else:
                values["sigma_log_ratio"] = normfit_sigma(ratio_log)
                values["sigma_log_depth"] = normfit_sigma(depth_log)
    for name, value in values.items():
        if value is not None and not np.isfinite(value):
            values[name] = None
            notes[name] = "形貌后处理产生非有限值，无法作为有效指标。"
    return values, notes


def _write_array_member(archive, name, shape, dtype, arrays):
    with archive.open(name + ".npy", "w", force_zip64=True) as member:
        np.lib.format.write_array_header_2_0(
            member, {"descr": np.lib.format.dtype_to_descr(dtype),
                     "fortran_order": False, "shape": shape})
        for array in arrays:
            array = np.ascontiguousarray(array)
            if array.dtype != dtype or array.dtype.hasobject:
                raise ValueError("阶段数组类型不一致或包含对象，不能安全导出")
            view = memoryview(array).cast("B")
            for offset in range(0, len(view), 1024 * 1024):
                member.write(view[offset:offset + 1024 * 1024])


def export_compatibility_npz(path: Path, stage_paths: list[Path]) -> None:
    """Create the legacy NPZ schema without stacking all stage volumes in RAM."""
    if not stage_paths:
        raise ValueError("没有已完成阶段可导出")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    mapping = {"perfect_result_sd": "perfect_result", "perfect_parameter_sd": "perfect_parameter",
               "a_sd": "perfect_a", "d_sd": "perfect_d", "cl_sd": "perfect_cl"}

    def stage_arrays(source, expected_shape):
        for stage_path in stage_paths:
            with np.load(stage_path, allow_pickle=False) as stage:
                array = stage[source]
                if array.shape != expected_shape:
                    raise ValueError("阶段状态数组维度不一致")
                yield array

    try:
        with temporary.open("wb") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED,
                                 allowZip64=True) as archive:
                for name, source in mapping.items():
                    with np.load(stage_paths[0], allow_pickle=False) as stage:
                        first = stage[source]
                        shape, dtype = first.shape, first.dtype
                    del first
                    _write_array_member(archive, name, (len(stage_paths), *shape), dtype,
                                        stage_arrays(source, shape))
                with np.load(stage_paths[-1], allow_pickle=False) as final:
                    for source in ("perfect_a", "perfect_d", "perfect_cl"):
                        array = final[source]
                        _write_array_member(archive, source, array.shape, array.dtype, (array,))
                        del array
                numbers = np.arange(1, len(stage_paths) + 1)
                _write_array_member(archive, "stage_numbers", numbers.shape, numbers.dtype, (numbers,))
            stream.flush()
            os.fsync(stream.fileno())
        _atomic_replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

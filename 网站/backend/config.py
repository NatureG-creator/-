"""Validated configuration for the web simulation runner."""

from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1] / "engine" / "01_运行程序与数据"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import unified_config as source_config  # noqa: E402


CONFIG_NAMES = (
    "GEOMETRY_CONFIG", "STAGE_GA_CONFIG", "SINGLE_STAGE_GA_CONFIG",
    "GA_CONFIG", "CA_CONFIG", "TAICHI_CONFIG", "POSTPROCESS_CONFIG",
    "MATLAB_CA_COMPARISON_CONFIG", "FIGURE_CONFIG", "FRACTURE_CONFIG",
)


def _jsonable(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def default_simulation_config() -> dict:
    config = {name: _jsonable(copy.deepcopy(getattr(source_config, name))) for name in CONFIG_NAMES}
    config["GA_PARAMETER_LOWER_BOUNDS"] = _jsonable(source_config.GA_PARAMETER_LOWER_BOUNDS)
    config["GA_PARAMETER_UPPER_BOUNDS"] = _jsonable(source_config.GA_PARAMETER_UPPER_BOUNDS)
    config["ACTIVE_STAGE_TARGET_DATA"] = _jsonable(source_config.ACTIVE_STAGE_TARGET_DATA)
    config["SINGLE_STAGE_TARGET_DATA"] = _jsonable(source_config.SINGLE_STAGE_TARGET_DATA)
    config["mode"] = "strict"
    config["TAICHI_CONFIG"]["use_taichi"] = False
    config["STAGE_GA_CONFIG"]["parallel_workers"] = 1
    return config


def validate_targets(value, run_mode: str) -> int:
    if run_mode not in {"single", "staged"}:
        raise ValueError("运行方式必须是 single 或 staged")
    if not isinstance(value, list) or not value or any(not isinstance(row, list) or len(row) != 6 for row in value):
        raise ValueError("目标数据必须为 N×6 数组")
    if run_mode == "single" and len(value) != 1:
        raise ValueError("单阶段目标必须恰好一行")
    for row in value:
        for number in row:
            if isinstance(number, bool) or not isinstance(number, (float, int)) or not math.isfinite(number):
                raise ValueError("目标六指标必须全部为有限数值")
    return len(value)


def _positive(config: dict, group: str, key: str, *, zero: bool = False):
    value = config[group][key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{group}.{key} 必须是有限数值")
    if value < 0 if zero else value <= 0:
        raise ValueError(f"{group}.{key} 必须{'非负' if zero else '大于0'}")


def validate_simulation_config(config: dict) -> dict:
    template = default_simulation_config()
    if not isinstance(config, dict):
        raise ValueError("模拟配置必须是对象")
    for name in CONFIG_NAMES:
        if not isinstance(config.get(name), dict) or set(config[name]) != set(template[name]):
            raise ValueError(f"{name} 的字段与统一配置不一致")
    for name in ("GA_PARAMETER_LOWER_BOUNDS", "GA_PARAMETER_UPPER_BOUNDS"):
        if not isinstance(config.get(name), list) or len(config[name]) != 10:
            raise ValueError(f"{name} 必须含10个参数")
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in config[name]):
            raise ValueError(f"{name} 必须为有限数值")
    if any(lo >= hi for lo, hi in zip(config["GA_PARAMETER_LOWER_BOUNDS"], config["GA_PARAMETER_UPPER_BOUNDS"])):
        raise ValueError("GA参数下界必须小于上界")
    for key in ("grid_w", "grid_l", "grid_n", "space_xy_um", "space_z_um"):
        _positive(config, "GEOMETRY_CONFIG", key)
    geometry = config["GEOMETRY_CONFIG"]
    if any(int(geometry[key]) != geometry[key] for key in ("grid_w", "grid_l", "grid_n")):
        raise ValueError("网格行列层数必须为整数")
    if geometry["grid_w"] * geometry["grid_l"] * geometry["grid_n"] > 5_000_000:
        raise ValueError("网格超过500万个元胞，请降低尺寸后运行")
    for group in ("STAGE_GA_CONFIG", "SINGLE_STAGE_GA_CONFIG"):
        for key in ("F", "nind", "selected_count", "maxgen", "parallel_workers"):
            _positive(config, group, key)
            if int(config[group][key]) != config[group][key]:
                raise ValueError(f"{group}.{key} 必须为整数")
        if config[group]["maxgen"] < 2:
            raise ValueError(f"{group}.maxgen 必须至少为2")
        if config[group]["selected_count"] > config[group]["nind"]:
            raise ValueError(f"{group}.selected_count 不得超过种群数")
    for key in ("sjb_divisor", "hist_bin_width", "depth_log_normalization"):
        _positive(config, "MATLAB_CA_COMPARISON_CONFIG", key)
    _positive(config, "MATLAB_CA_COMPARISON_CONFIG", "min_distance", zero=True)
    for key in ("surface_dpi", "mesh_dpi", "auto_plot_dpi"):
        _positive(config, "FIGURE_CONFIG", key)
    try:
        from matplotlib import colormaps
        for key in ("surface_cmap", "mesh_cmap"):
            if config["FIGURE_CONFIG"][key] not in colormaps:
                raise ValueError(f"FIGURE_CONFIG.{key} 不是有效配色")
    except ImportError:
        pass
    if config.get("mode") not in {"strict", "fast"}:
        raise ValueError("mode 必须为 strict 或 fast")
    if config["mode"] == "strict":
        if config["TAICHI_CONFIG"]["use_taichi"]:
            raise ValueError("严格可复现模式要求 use_taichi=false")
        if config["STAGE_GA_CONFIG"]["parallel_workers"] != 1:
            raise ValueError("严格可复现模式要求 parallel_workers=1")
    seed = config["GA_CONFIG"]["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise ValueError("GA_CONFIG.seed 必须为0到2^32-1的整数")
    validate_targets(config["ACTIVE_STAGE_TARGET_DATA"], "staged")
    if not isinstance(config["SINGLE_STAGE_TARGET_DATA"], list) or len(config["SINGLE_STAGE_TARGET_DATA"]) != 6:
        raise ValueError("SINGLE_STAGE_TARGET_DATA 必须含6项")
    validate_targets([config["SINGLE_STAGE_TARGET_DATA"]], "single")
    try:
        json.dumps(config, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("配置包含不可序列化或非有限值") from exc
    return config

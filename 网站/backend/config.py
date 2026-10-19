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

PATH_DIRECTORY_KEYS = ("inputs", "outputs", "auto_plots", "morphology_outputs", "curve_outputs", "curves_dir")
PATH_FILE_KEYS = ("fracture_test_data", "material_test_data", "long_term_corrosion_data", "curve_metadata")


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
    config = {name: _jsonable(copy.deepcopy(value))
              for name, value in vars(source_config).items() if name.isupper()}
    config["mode"] = "strict"
    config["TAICHI_CONFIG"]["use_taichi"] = False
    config["STAGE_GA_CONFIG"]["parallel_workers"] = 1
    return config


def website_default_simulation_config() -> dict:
    """默认网页任务走 PyCharm 对应的 NumPy 进程池路径。"""
    config = default_simulation_config()
    config["mode"] = "pycharm"
    config["TAICHI_CONFIG"]["use_taichi"] = False
    for group in ("STAGE_GA_CONFIG", "SINGLE_STAGE_GA_CONFIG"):
        config[group]["parallel_workers"] = 10
    return config


def validate_value(value, original, path: str):
    """校验 JSON 类型；布尔值不能伪装成数字，数组不能漏校验。"""
    if isinstance(original, bool):
        valid = isinstance(value, bool)
    elif isinstance(original, int):
        valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                 and math.isfinite(value) and value == int(value))
    elif isinstance(original, float):
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    elif isinstance(original, str):
        valid = isinstance(value, str) and len(value) <= 4096
    elif original is None:
        valid = value is None or (not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value))
    elif isinstance(original, dict):
        valid = isinstance(value, dict) and set(value) == set(original)
        if valid:
            for key, item in original.items():
                validate_value(value[key], item, f"{path}.{key}")
    elif isinstance(original, list):
        valid = isinstance(value, list) and len(value) == len(original)
        if valid:
            for index, item in enumerate(original):
                validate_value(value[index], item, f"{path}[{index}]")
    else:
        valid = False
    if not valid:
        raise ValueError(f"{path} 的类型、数组长度或数值无效")


def validate_path_config(path_config: dict) -> dict:
    """校验网页提交的研究数据路径；路径本身由用户决定，但不能为空或含 NUL。"""
    if not isinstance(path_config, dict):
        raise ValueError("PATH_CONFIG 必须是对象")
    expected = set(PATH_DIRECTORY_KEYS) | set(PATH_FILE_KEYS)
    if set(path_config) != expected:
        raise ValueError("PATH_CONFIG 的字段与统一配置不一致")
    for key, value in path_config.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"PATH_CONFIG.{key} 必须是非空路径")
        if "\x00" in value:
            raise ValueError(f"PATH_CONFIG.{key} 不能包含 NUL 字符")
        if len(value) > 32760:
            raise ValueError(f"PATH_CONFIG.{key} 路径过长")
    return path_config


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
        validate_value(config[name], template[name], name)
    unknown = set(config) - set(template)
    if unknown:
        raise ValueError(f"未知模拟配置：{', '.join(sorted(unknown))}")
    for name in ("ROOT", "PATH_CONFIG", "TARGET_SOURCE"):
        if name in config:
            validate_value(config[name], template[name], name)
    if "PATH_CONFIG" not in config:
        raise ValueError("缺少 PATH_CONFIG")
    validate_path_config(config["PATH_CONFIG"])
    if "MULTI_CASE_CONFIG" in config:
        multi = config["MULTI_CASE_CONFIG"]
        original = template["MULTI_CASE_CONFIG"]
        if not isinstance(multi, dict) or set(multi) != set(original):
            raise ValueError("MULTI_CASE_CONFIG 的字段与统一配置不一致")
        for key, value in original.items():
            if key != "cases":
                validate_value(multi[key], value, f"MULTI_CASE_CONFIG.{key}")
        cases = multi["cases"]
        if not isinstance(cases, list) or not cases:
            raise ValueError("MULTI_CASE_CONFIG.cases 必须为至少一个工况的数组")
        names = set()
        for index, case in enumerate(cases):
            path = f"MULTI_CASE_CONFIG.cases[{index}]"
            allowed = {"case_name", "matlab_target", "mode", "upload_id", "variable",
                       "orientation", "targets", "simulation_mode"}
            if not isinstance(case, dict) or "case_name" not in case or set(case) - allowed:
                raise ValueError(f"{path} 必须包含case_name，字段只能为 {' / '.join(sorted(allowed))}")
            if not ({"matlab_target", "upload_id", "targets"} & set(case)):
                raise ValueError(f"{path} 必须指定matlab_target、upload_id或targets")
            for key in ("case_name", "matlab_target", "upload_id", "variable"):
                if key not in case:
                    continue
                if key == "variable" and case[key] is None:
                    continue
                validate_value(case[key], "", f"{path}.{key}")
                if key != "variable" and not case[key].strip():
                    raise ValueError(f"{path}.{key} 不能为空")
            if case["case_name"] in names:
                raise ValueError(f"{path}.case_name 工况名不得重复")
            names.add(case["case_name"])
            if "mode" in case and (not isinstance(case["mode"], str) or case["mode"] not in {"sequential", "parallel"}):
                raise ValueError(f"{path}.mode 必须为 sequential 或 parallel")
            if "orientation" in case and (not isinstance(case["orientation"], str) or case["orientation"] not in {"auto", "rows", "columns"}):
                raise ValueError(f"{path}.orientation 必须为 auto、rows或columns")
            if "simulation_mode" in case and (not isinstance(case["simulation_mode"], str) or case["simulation_mode"] not in {"single", "staged"}):
                raise ValueError(f"{path}.simulation_mode 必须为 single或staged")
            if "targets" in case:
                validate_targets(case["targets"], case.get("simulation_mode", "staged"))
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
    for group, values in config.items():
        if group not in CONFIG_NAMES:
            continue
        for key, value in values.items():
            if key.endswith("_figsize") or key.endswith("_panel_size") or key in {"surface_panel_size", "mesh_panel_size"}:
                if any(item <= 0 for item in value):
                    raise ValueError(f"{group}.{key} 尺寸必须大于0")
            if key.endswith("_dpi"):
                _positive(config, group, key)
    for group, keys in {
        "GA_CONFIG": ("bits_per_param", "sigma_share"),
        "POSTPROCESS_CONFIG": ("interactive_window_size", "auto_plot_window_size", "conv2_window_size", "expand_factor", "neighborhood", "log_normalization"),
        "FRACTURE_CONFIG": ("minimum_experiment_samples", "curve_points", "curve_sustain_points", "y0"),
    }.items():
        for key in keys:
            _positive(config, group, key)
    for group, keys in {
        "CA_CONFIG": ("initial_d", "initial_cl", "initial_enhancement_steps", "initial_enhancement_beta", "convex_height_limit"),
        "POSTPROCESS_CONFIG": ("gaussian_sigma", "min_prominence", "min_distance", "ca_min_prominence", "ca_min_distance"),
        "MATLAB_CA_COMPARISON_CONFIG": ("min_prominence",),
        "FIGURE_CONFIG": ("surface_linewidth",),
    }.items():
        for key in keys:
            _positive(config, group, key, zero=True)
    _positive(config, "GEOMETRY_CONFIG", "plate_thickness_um")
    for group, key in (("GA_CONFIG", "base_px"), ("GA_CONFIG", "base_pm"),
                       ("GA_CONFIG", "decay_rate"), ("CA_CONFIG", "alpha_passive"),
                       ("POSTPROCESS_CONFIG", "watershed_threshold"),
                       ("FRACTURE_CONFIG", "curve_drop_ratio")):
        if not 0 <= config[group][key] <= 1:
            raise ValueError(f"{group}.{key} 必须在[0,1]范围内")
    for group, key, choices in (
        ("TAICHI_CONFIG", "arch", {"cpu"}),
        ("MATLAB_CA_COMPARISON_CONFIG", "depth_log_scale", {"space_z", "raw"}),
    ):
        if config[group][key] not in choices:
            raise ValueError(f"{group}.{key} 必须为 {' / '.join(sorted(choices))}")
    if config.get("TARGET_SOURCE", "matlab") not in {"matlab", "manual"}:
        raise ValueError("TARGET_SOURCE 必须为 matlab 或 manual")
    if "MULTI_CASE_CONFIG" in config:
        multi = config["MULTI_CASE_CONFIG"]
        if multi["run_mode"] not in {"single", "sequential", "parallel", "mixed"}:
            raise ValueError("MULTI_CASE_CONFIG.run_mode 无效")
        _positive(config, "MULTI_CASE_CONFIG", "parallel_case_workers")
    try:
        from matplotlib import colormaps
        for key in ("surface_cmap", "mesh_cmap"):
            if config["FIGURE_CONFIG"][key] not in colormaps:
                raise ValueError(f"FIGURE_CONFIG.{key} 不是有效配色")
    except ImportError:
        pass
    if config.get("mode") not in {"strict", "pycharm", "fast"}:
        raise ValueError("mode 必须为 strict、pycharm 或 fast")
    if config["mode"] == "strict":
        if config["TAICHI_CONFIG"]["use_taichi"]:
            raise ValueError("严格可复现模式要求 use_taichi=false")
        if config["STAGE_GA_CONFIG"]["parallel_workers"] != 1:
            raise ValueError("严格可复现模式要求 parallel_workers=1")
    if config["mode"] == "pycharm" and config["TAICHI_CONFIG"]["use_taichi"]:
        raise ValueError("PyCharm模式要求 use_taichi=false")
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

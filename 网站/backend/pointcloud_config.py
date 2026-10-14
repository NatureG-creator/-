"""Expose every step00 parameter with its source comment and safe JSON value."""

from __future__ import annotations

import math
import re
from pathlib import Path

from .config import validate_value
from .parameter_catalog import value_type

SOURCE = Path(__file__).resolve().parents[1] / "matlab" / "step00_corrosion_config.m"
ASSIGNMENT = re.compile(r"^\s*cfg\.(\w+)\.(\w+)\s*=\s*(.+?)\s*;\s*(?:%.*)?$")
REFERENCE = re.compile(r"^cfg\.(\w+)\.(\w+)$")
LABELS = {
    "point_cloud_190_pattern": "完整参考扫描文件", "point_cloud_50_file": "局部腐蚀扫描文件",
    "edge_processing_file": "裁边输入文件", "flat_column_count": "左侧参考区列数",
    "corrosion_column_count": "中央腐蚀区列数", "flat_height_ratio": "参考高度极差比例",
    "grid_resolution_mm": "点云网格间距 / mm", "trim_edge_rows": "裁边网格数",
    "trim_legacy_asymmetric": "沿用历史非对称裁边", "main_gaussian_sigma": "主流程高斯平滑强度",
    "remove_edge_ratio": "四周裁边比例", "invert_z_on_load": "读取时反转 Z 符号",
    "reverse_z_after_edge_removal": "裁边后反转 Z", "interpolation_method": "散乱点插值方法",
    "missing_fill_method": "缺失网格填补方法", "min_prominence": "极值最低突出程度",
    "min_distance": "坑中心最小网格距离", "neighborhood": "极值搜索邻域",
    "edge_margin": "极值检测边缘留白", "depth_reference_mode": "坑深参考面定义",
    "diameter_mode": "坑径计算定义", "threshold": "分水岭边界阈值",
    "gaussian_sigma": "分水岭高斯平滑强度", "local_contrast_window": "局部对比度窗口",
    "local_contrast_factor": "局部对比度阈值系数", "gradient_barrier_value": "梯度屏障值",
    "gradient_operator": "梯度算子", "boundary_holes": "区域孔洞边界",
    "depth_mm_to_um": "坑深 mm 转 μm 系数", "sjb_reciprocal_numerator": "深径比倒数分子",
    "hist_bin_width": "直方图柱宽", "hist_normalization": "直方图归一化",
    "hist_face_color": "直方图 RGB 颜色", "fit_distribution": "分布拟合模型",
    "fit_curve_points": "拟合曲线点数", "fit_line_width": "拟合曲线线宽",
    "point_cloud_marker_size": "点云显示点大小", "deleted_point_marker_size": "删除点显示大小",
    "extrema_marker_size": "极值点大小", "boundary_marker_size": "边界点大小",
    "extrema_cross_size": "极值十字标记大小", "extrema_cross_line_width": "极值十字线宽",
    "boundary_line_width": "边界线宽", "contour_levels": "等高线层数",
    "extrema_figure_position": "极值图窗口位置与尺寸", "reverse_compare_position": "反转对比窗口位置与尺寸",
    "surface_colormap": "曲面配色", "processed_surface_colormap": "处理后曲面配色",
    "watershed_colormap": "分水岭配色", "surface_view": "曲面方位与仰角",
    "watershed_view": "分水岭方位与仰角", "processed_surface_view": "处理后曲面视图维数",
    "font_size": "字体大小", "font_name": "字体名称", "surface_clim": "历史曲面色标范围",
    "dx_mm": "APDL X 方向间距 / mm", "dy_mm": "APDL Y 方向间距 / mm",
    "grid_matrix_variable": "APDL 高程矩阵变量", "x_start_mm": "APDL X 起点 / mm",
    "y_start_mm": "APDL Y 起点 / mm", "delimiter": "导出文本分隔符",
    "precision": "导出数字精度", "newline": "导出换行格式",
    "pit_statistics_excel": "坑深统计表文件", "edge_removed_txt": "裁边点云文件",
    "edge_reversed_txt": "反转点云文件", "apdl_x_txt": "APDL X 坐标文件",
    "apdl_y_txt": "APDL Y 坐标文件", "apdl_z_txt": "APDL Z 坐标文件",
}


def _value(expression: str, prior: dict):
    expression = expression.strip()
    if expression in ("true", "false"):
        return expression == "true"
    if expression.startswith("'") and expression.endswith("'"):
        return expression[1:-1]
    if expression.startswith("[") and expression.endswith("]"):
        return [float(item) for item in re.split(r"[\s,]+", expression[1:-1].strip()) if item]
    reference = REFERENCE.fullmatch(expression)
    if reference:
        return prior.get((reference.group(1), reference.group(2)))
    if expression.startswith("fullfile("):
        return ""
    if expression.startswith("sprintf("):
        return "\t"
    try:
        number = float(expression)
        return int(number) if number.is_integer() else number
    except ValueError:
        return None


def catalog() -> list[dict]:
    comments = []
    prior = {}
    entries = []
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("%"):
            comments.append(stripped.lstrip("% "))
            comments = comments[-3:]
            continue
        match = ASSIGNMENT.match(line)
        if match:
            group, key, expression = match.groups()
            if (group, key) in prior:
                continue
            value = _value(expression, prior)
            prior[(group, key)] = value
            inline = line.split("%", 1)[1].strip() if "%" in line else ""
            help_text = comments[-1] if comments else inline
            label = LABELS.get(key, (help_text or key).split("。")[0].split("；")[0])
            label = label.replace("190 mm", "完整参考").replace("50 mm", "局部")
            entries.append({"path": f"{group}.{key}", "group": group, "key": key, "value": value,
                            "help": help_text or key,
                            "label": label, "type": value_type(value),
                            "scope": "任务管理" if group in {"input", "output"} else "点云分析",
                            "editable": group not in {"input", "output"}})
        if stripped and not stripped.startswith("%"):
            comments.clear()
    return entries


def default_pointcloud_config() -> dict:
    config = {}
    for item in catalog():
        config.setdefault(item["group"], {})[item["key"]] = item["value"]
    return config


def validate_pointcloud_config(config: dict) -> dict:
    defaults = default_pointcloud_config()
    if not isinstance(config, dict):
        raise ValueError("点云参数必须为对象")
    for group, values in config.items():
        if group not in defaults or not isinstance(values, dict):
            raise ValueError(f"未知点云参数分组：{group}")
        if group in {"input", "output"}:
            raise ValueError("输入输出文件请使用上传和结果下载区域")
        for key, value in values.items():
            if key not in defaults[group]:
                raise ValueError(f"未知点云参数：{group}.{key}")
            original = defaults[group][key]
            validate_value(value, original, f"{group}.{key}")
    merged = {group: dict(values) for group, values in defaults.items()}
    for group, values in config.items():
        merged[group].update(values)
    for key in ("dx_mm", "dy_mm"):
        if key not in config.get("apdl", {}):
            merged["apdl"][key] = merged["preprocessing"]["grid_resolution_mm"]
    for group, key in (("preprocessing", "grid_resolution_mm"),
                       ("distribution", "depth_mm_to_um"),
                       ("distribution", "hist_bin_width"),
                       ("reference", "flat_column_count"),
                       ("reference", "corrosion_column_count"),
                       ("distribution", "fit_curve_points"), ("distribution", "fit_line_width"),
                       ("watershed", "local_contrast_window"),
                       ("apdl", "dx_mm"), ("apdl", "dy_mm")):
        if merged[group][key] <= 0:
            raise ValueError(f"{group}.{key} 必须大于0")
    if not 0 <= merged["preprocessing"]["remove_edge_ratio"] < 0.5:
        raise ValueError("preprocessing.remove_edge_ratio 必须在[0,0.5)范围内")
    if not 0 < merged["watershed"]["threshold"] < 1:
        raise ValueError("watershed.threshold 必须在(0,1)范围内")
    if merged["pit_detection"]["min_distance"] < 0:
        raise ValueError("pit_detection.min_distance 不得小于0")
    for group, keys in {
        "preprocessing": ("trim_edge_rows", "main_gaussian_sigma"),
        "pit_detection": ("min_prominence", "edge_margin"),
        "watershed": ("gaussian_sigma", "local_contrast_factor", "gradient_barrier_value"),
    }.items():
        for key in keys:
            if merged[group][key] < 0:
                raise ValueError(f"{group}.{key} 必须非负")
    if not 0 <= merged["reference"]["flat_height_ratio"] <= 1:
        raise ValueError("reference.flat_height_ratio 必须在[0,1]范围内")
    neighborhood = merged["pit_detection"]["neighborhood"]
    if any(item < 1 or item != int(item) for item in neighborhood) or neighborhood[0] != neighborhood[1]:
        raise ValueError("pit_detection.neighborhood 必须为两个相同的正整数（当前Python校准要求方形邻域）")
    enums = {
        ("preprocessing", "interpolation_method"): {"linear", "nearest", "natural"},
        ("preprocessing", "missing_fill_method"): {"nearest", "linear"},
        ("pit_detection", "depth_reference_mode"): {"global_minimum"},
        ("pit_detection", "diameter_mode"): {"mean_xy_span"},
        ("watershed", "gradient_operator"): {"sobel", "prewitt", "central", "intermediate", "roberts"},
        ("watershed", "boundary_holes"): {"holes", "noholes"},
        ("distribution", "hist_normalization"): {"pdf", "probability", "count", "countdensity", "cumcount", "cdf"},
        ("distribution", "fit_distribution"): {"Normal"},
        ("apdl", "grid_matrix_variable"): {"Z_filled", "F_filled"},
        ("apdl", "newline"): {"pc", "unix"},
    }
    for (group, key), choices in enums.items():
        if merged[group][key] not in choices:
            raise ValueError(f"{group}.{key} 必须为 {' / '.join(sorted(choices))}")
    for group, key in (("distribution", "hist_face_color"),):
        if any(item < 0 or item > 1 for item in merged[group][key]):
            raise ValueError(f"{group}.{key} RGB分量必须在[0,1]范围内")
    for key in ("extrema_figure_position", "reverse_compare_position"):
        if any(item <= 0 for item in merged["figure"][key][2:]):
            raise ValueError(f"figure.{key} 的宽高必须大于0")
    if merged["figure"]["surface_clim"][0] >= merged["figure"]["surface_clim"][1]:
        raise ValueError("figure.surface_clim 下限必须小于上限")
    for key, value in merged["figure"].items():
        if isinstance(value, (int, float)) and key != "processed_surface_view" and value <= 0:
            raise ValueError(f"figure.{key} 必须大于0")
        if key.endswith("_colormap") and not re.fullmatch(r"[A-Za-z]\w*", value):
            raise ValueError(f"figure.{key} 配色名称无效")
    if merged["figure"]["processed_surface_view"] not in (2, 3):
        raise ValueError("figure.processed_surface_view 必须为2或3")
    if not re.fullmatch(r"%\.\d{1,2}[feg]", merged["apdl"]["precision"]):
        raise ValueError("apdl.precision 必须为 %.6f 等有效数字格式")
    if merged["distribution"]["depth_mm_to_um"] != 1000:
        raise ValueError("与Python六指标接口联动时 depth_mm_to_um 必须为1000")
    if merged["distribution"]["sjb_reciprocal_numerator"] != 1:
        raise ValueError("与Python六指标接口联动时 sjb_reciprocal_numerator 必须为1")
    return {group: values for group, values in merged.items() if group not in {"input", "output"}}

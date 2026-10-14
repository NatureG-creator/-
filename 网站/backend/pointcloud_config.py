"""Expose every step00 parameter with its source comment and safe JSON value."""

from __future__ import annotations

import math
import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "matlab" / "step00_corrosion_config.m"
ASSIGNMENT = re.compile(r"^\s*cfg\.(\w+)\.(\w+)\s*=\s*(.+?)\s*;\s*(?:%.*)?$")
REFERENCE = re.compile(r"^cfg\.(\w+)\.(\w+)$")


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
            entries.append({"group": group, "key": key, "value": value,
                            "help": help_text or key,
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
            if isinstance(original, bool):
                valid = isinstance(value, bool)
            elif isinstance(original, (float, int)):
                valid = not isinstance(value, bool) and isinstance(value, (float, int)) and math.isfinite(value)
            elif isinstance(original, list):
                valid = isinstance(value, list) and len(value) == len(original) and all(
                    isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x) for x in value)
            else:
                valid = isinstance(value, str) and len(value) < 100
            if not valid:
                raise ValueError(f"{group}.{key} 的类型或数值无效")
    merged = {group: dict(values) for group, values in defaults.items()}
    for group, values in config.items():
        merged[group].update(values)
    for group, key in (("preprocessing", "grid_resolution_mm"),
                       ("distribution", "depth_mm_to_um"),
                       ("distribution", "hist_bin_width"),
                       ("reference", "flat_column_count"),
                       ("reference", "corrosion_column_count")):
        if merged[group][key] <= 0:
            raise ValueError(f"{group}.{key} 必须大于0")
    if not 0 <= merged["preprocessing"]["remove_edge_ratio"] < 0.5:
        raise ValueError("preprocessing.remove_edge_ratio 必须在[0,0.5)范围内")
    if not 0 < merged["watershed"]["threshold"] < 1:
        raise ValueError("watershed.threshold 必须在(0,1)范围内")
    if merged["pit_detection"]["min_distance"] < 0:
        raise ValueError("pit_detection.min_distance 不得小于0")
    if merged["distribution"]["depth_mm_to_um"] != 1000:
        raise ValueError("与Python六指标接口联动时 depth_mm_to_um 必须为1000")
    if merged["distribution"]["sjb_reciprocal_numerator"] != 1:
        raise ValueError("与Python六指标接口联动时 sjb_reciprocal_numerator 必须为1")
    return {group: values for group, values in merged.items() if group not in {"input", "output"}}

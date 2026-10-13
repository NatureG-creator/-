"""读取并汇总第二步 stage_moni 生成的 NPZ 结果。

在 PyCharm 中直接运行本文件即可。默认读取本文件同目录下的
``step2_stage_moni_result.npz``，不会修改原始结果文件。

也可以在 PyCharm 的“程序实参”中填写另一个 .npz 文件路径，
或在终端中运行：``python 10_read_step2_result.py 结果文件.npz``。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parent
DEFAULT_RESULT_PATH = Path(
    r"E:/CODEX文件/python腐蚀代码/腐蚀代码7_高速版_MATLAB实测接口/01_运行程序与数据/结果文件/step2_stage_moni_result10z.npz"
)

# perfect_parameter_sd 中 10 个最优参数的固定排列顺序。
PARAMETER_INFO = (
    ("p_uniform_base", "均匀腐蚀基础概率"),
    ("p_passive_base", "钝化基础概率"),
    ("p_break", "钝化膜破裂概率"),
    ("cl_threshold", "氯离子腐蚀阈值"),
    ("alpha_corrosion", "腐蚀反应系数"),
    ("sensitive_point", "敏感点参数"),
    ("alpha_p_break", "破膜概率调节系数"),
    ("p_h", "水平方向扩展概率"),
    ("p_v", "竖直方向扩展概率"),
    ("p_o", "其他方向扩展参数"),
)

ERROR_WEIGHTS = np.asarray([0.1, 0.3, 0.2, 0.4], dtype=float)


def format_elapsed_time(seconds: float | None) -> str:
    """NPZ 中保存秒数，显示时除以 3600 转成小时；兼容没有计时字段的旧文件。"""
    if seconds is None:
        return "结果文件中未保存运行时间"
    seconds = float(seconds)
    if not np.isfinite(seconds) or seconds < 0:
        raise ValueError("elapsed_seconds 必须为非负有限秒数")
    return f"{seconds:.2f} s ({seconds / 3600.0:.4f} 小时)"


def load_result(path: Path | str) -> dict[str, np.ndarray]:
    """读取 NPZ 文件并返回普通字典，兼容其中的 object 数组。"""
    result_path = Path(path).expanduser().resolve()
    if not result_path.exists():
        raise FileNotFoundError(f"找不到结果文件：{result_path}")
    if result_path.suffix.lower() != ".npz":
        raise ValueError(f"结果文件必须是 .npz 格式：{result_path}")

    with np.load(result_path, allow_pickle=True) as npz_file:
        return {name: npz_file[name] for name in npz_file.files}


def calculate_weighted_error(error_values: np.ndarray) -> float:
    """按 MATLAB 原逻辑的四项权重计算综合误差。"""
    flat_values = np.asarray(error_values, dtype=float).reshape(-1)
    if flat_values.size != ERROR_WEIGHTS.size:
        raise ValueError(
            f"误差指标应有 {ERROR_WEIGHTS.size} 项，实际读取到 {flat_values.size} 项。"
        )
    return float(flat_values @ ERROR_WEIGHTS)


def to_json_value(value: Any) -> Any:
    """将 NumPy 标量或数组转换为可写入 JSON 的 Python 数据。"""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def numeric_array_summary(value: np.ndarray) -> dict[str, Any]:
    """只统计数值数组摘要，避免把大型三维数组全部打印出来。"""
    array = np.asarray(value)
    summary: dict[str, Any] = {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "size": int(array.size),
    }

    if array.dtype == object:
        summary["note"] = "object 数组，仅记录结构，不展开全部内容"
        return summary

    if array.size == 0:
        summary["note"] = "空数组"
        return summary

    numeric = np.asarray(array, dtype=float)
    finite = numeric[np.isfinite(numeric)]
    if finite.size == 0:
        summary["note"] = "数组中没有有限数值"
        return summary

    summary.update(
        {
            "min": float(np.min(finite)),
            "max": float(np.max(finite)),
            "mean": float(np.mean(finite)),
        }
    )
    return summary


def scalar_value(result: dict[str, np.ndarray], key: str) -> Any:
    """读取一个可选的 NumPy 标量；字段不存在时返回 None。"""
    if key not in result:
        return None
    value = np.asarray(result[key])
    return to_json_value(value.item()) if value.size == 1 else to_json_value(value)


def build_summary(result_path: Path, result: dict[str, np.ndarray]) -> dict[str, Any]:
    """构造控制台显示和 JSON 导出共用的结果摘要。"""
    required = ("perfect_result_sd", "perfect_parameter_sd")
    missing = [name for name in required if name not in result]
    if missing:
        raise KeyError(f"结果文件缺少必要字段：{', '.join(missing)}")

    errors = np.asarray(result["perfect_result_sd"], dtype=float).reshape(-1)
    parameters = np.asarray(result["perfect_parameter_sd"], dtype=float).reshape(-1)
    if parameters.size != len(PARAMETER_INFO):
        raise ValueError(
            f"最优参数应有 {len(PARAMETER_INFO)} 个，实际读取到 {parameters.size} 个。"
        )

    parameter_rows = [
        {
            "index": index,
            "name": name,
            "meaning": meaning,
            "value": float(value),
        }
        for index, ((name, meaning), value) in enumerate(
            zip(PARAMETER_INFO, parameters, strict=True), start=1
        )
    ]

    array_summaries = {
        key: numeric_array_summary(result[key])
        for key in ("a_sd", "d_sd", "cl_sd", "perfect_a", "perfect_d", "perfect_cl")
        if key in result
    }

    # 秒数来自第二步保存的记录，不使用当前读取程序的运行时间代替。
    elapsed_seconds = scalar_value(result, "elapsed_seconds")
    if elapsed_seconds is not None:
        elapsed_seconds = float(elapsed_seconds)
        format_elapsed_time(elapsed_seconds)

    return {
        "source_file": str(result_path),
        "fields": list(result.keys()),
        "stage_numbers": to_json_value(result.get("stage_numbers", np.asarray([]))),
        "seed": scalar_value(result, "seed"),
        "elapsed_seconds": elapsed_seconds,
        "elapsed_hours": None if elapsed_seconds is None else elapsed_seconds / 3600.0,
        "space_xy_um": scalar_value(result, "space_xy_um"),
        "space_z_um": scalar_value(result, "space_z_um"),
        "error_values": errors.tolist(),
        "error_weights": ERROR_WEIGHTS.tolist(),
        "weighted_error": calculate_weighted_error(errors),
        "optimal_parameters": parameter_rows,
        "target_data": to_json_value(result.get("target_data", np.asarray([]))),
        "array_summaries": array_summaries,
    }


def print_summary(summary: dict[str, Any]) -> None:
    """用适合初学者查看的中文格式输出结果摘要。"""
    print("=" * 72)
    print("第二步 stage_moni 结果读取成功")
    print("=" * 72)
    print(f"结果文件：{summary['source_file']}")
    print(f"包含字段：{', '.join(summary['fields'])}")
    print(f"阶段编号：{summary['stage_numbers']}")
    print(f"随机种子：{summary['seed']}")
    print(f"第二步运行时间：{format_elapsed_time(summary['elapsed_seconds'])}")
    print(f"X/Y 元胞尺寸：{summary['space_xy_um']} μm")
    print(f"Z 元胞尺寸：{summary['space_z_um']} μm")

    print("\n[四项最优误差]")
    for index, (value, weight) in enumerate(
        zip(summary["error_values"], summary["error_weights"], strict=True), start=1
    ):
        print(f"  误差 {index}: {value:.12g}，权重 {weight:.1f}")
    print(f"  加权综合误差：{summary['weighted_error']:.12g}")

    print("\n[10 个最优参数]")
    for row in summary["optimal_parameters"]:
        print(
            f"  {row['index']:>2}. {row['name']:<20} "
            f"= {row['value']:.12g}  # {row['meaning']}"
        )

    print("\n[目标数据 target_data]")
    print(f"  {summary['target_data']}")

    print("\n[大型状态数组摘要，不展开全部元胞]")
    for name, array_summary in summary["array_summaries"].items():
        print(f"  {name}: {array_summary}")


def parse_args() -> argparse.Namespace:
    """解析可选的 NPZ 路径和 JSON 输出路径。"""
    parser = argparse.ArgumentParser(description="读取第二步 stage_moni 的 NPZ 结果")
    parser.add_argument(
        "result_file",
        nargs="?",
        type=Path,
        default=DEFAULT_RESULT_PATH,
        help="要读取的 .npz 文件；不填写时读取文件开头 DEFAULT_RESULT_PATH 指定的文件",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="JSON 汇总文件路径；默认保存在结果文件同目录",
    )
    return parser.parse_args()


def main() -> int:
    """程序入口：读取、显示并导出 JSON 摘要。"""
    args = parse_args()
    result_path = args.result_file.expanduser().resolve()
    json_path = (
        args.json.expanduser().resolve()
        if args.json is not None
        else result_path.with_name("step2_result_summary.json")
    )

    try:
        result = load_result(result_path)
        summary = build_summary(result_path, result)
        print_summary(summary)
        # json_path.write_text(
        #     json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        # )
    except (FileNotFoundError, ValueError, KeyError, OSError) as exc:
        print(f"\n读取失败：{exc}")
        return 1

    print(f"\nJSON 汇总已保存：{json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

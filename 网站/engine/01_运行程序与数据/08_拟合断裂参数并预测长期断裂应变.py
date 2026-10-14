"""第八步：10 组试验拟合 + 目标腐蚀深度下的断裂应变预测。

本脚本暂不连接 Abaqus。试验断裂应变 epsilon_n_f 必须由用户从拉伸试验曲线整理后
写入 inputs/fracture_test_data.csv；长期的 ds 和 lambda_rho 可来自 CA/点云后处理。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import importlib.util
import time
from pathlib import Path
from typing import Iterable

import numpy as np
from scipy.optimize import least_squares

from unified_config import FRACTURE_CONFIG, PATH_CONFIG


# 采用文件路径加载第二步，兼容中文文件名、直接运行和 pytest 的路径加载方式。
_extract_spec = importlib.util.spec_from_file_location(
    "extract_fracture_strain_step", Path(__file__).with_name("07_自动提取试验断裂应变.py")
)
if _extract_spec is None or _extract_spec.loader is None:
    raise ImportError("无法加载 07_自动提取试验断裂应变.py")
_extract_module = importlib.util.module_from_spec(_extract_spec)
_extract_spec.loader.exec_module(_extract_module)
extract_from_metadata = _extract_module.extract_from_metadata


DEFAULT_Y0 = float(FRACTURE_CONFIG["y0"])


def _positive(name: str, values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=np.float64).reshape(-1)
    if array.size == 0 or not np.all(np.isfinite(array)) or np.any(array <= 0):
        raise ValueError(f"{name} 必须是非空且全部为正的有限数值")
    return array


def _finite(name: str, values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=np.float64).reshape(-1)
    if array.size == 0 or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} 必须是非空有限数值")
    return array


def predict_by_fitted_ratio(
    ds: Iterable[float], shape: Iterable[float], ratio: float, c: float, n: float, y0: float = DEFAULT_Y0
) -> np.ndarray:
    """按 epsilon=[ratio/(ds*exp(y0+c*lambda_rho))]^(1/n) 计算名义断裂应变。"""
    ds_array = _positive("ds", ds)
    shape_array = _finite("lambda_rho", shape)
    if ds_array.shape != shape_array.shape:
        raise ValueError("ds 和 lambda_rho 长度必须一致")
    if ratio <= 0 or n <= 0:
        raise ValueError("ratio 和 n 必须为正数")
    return (float(ratio) / (ds_array * np.exp(float(y0) + float(c) * shape_array))) ** (1.0 / float(n))


def load_experiment_data(path: str | Path, min_samples: int = 10) -> list[dict[str, float | str]]:
    """读取试验数据，并强制检查至少 10 组有效数据。"""
    rows: list[dict[str, float | str]] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"sample_id", "ds", "lambda_rho", "epsilon_n_f"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"试验数据缺少列: {', '.join(sorted(missing))}")
        for row in reader:
            if not any(str(value).strip() for value in row.values()):
                continue
            rows.append({
                "sample_id": str(row["sample_id"]),
                "ds": float(row["ds"]),
                "lambda_rho": float(row["lambda_rho"]),
                "epsilon_n_f": float(row["epsilon_n_f"]),
            })
    if len(rows) < min_samples:
        raise ValueError(f"试验数据至少需要 {min_samples} 组，当前只有 {len(rows)} 组")
    _positive("ds", [row["ds"] for row in rows])
    _finite("lambda_rho", [row["lambda_rho"] for row in rows])
    _positive("epsilon_n_f", [row["epsilon_n_f"] for row in rows])
    return rows


def fit_parameters(data: list[dict[str, float | str]], y0: float = DEFAULT_Y0) -> dict[str, float | int | bool | str | None]:
    """拟合可识别的 ratio=eta_sp/K_sp、c=C_sp 和 n=n_sp。"""
    ds = _positive("ds", [row["ds"] for row in data])
    shape = _finite("lambda_rho", [row["lambda_rho"] for row in data])
    measured = _positive("epsilon_n_f", [row["epsilon_n_f"] for row in data])
    design = np.column_stack([np.ones_like(ds), np.log(ds), shape])
    coeff, *_ = np.linalg.lstsq(design, np.log(measured), rcond=None)
    b0, b1, b2 = coeff
    n0 = max(2.0, min(10.0, -1.0 / b1)) if b1 < 0 else 2.0
    c0 = b2 / b1 if b1 < 0 else 1.0
    log_ratio0 = b0 * n0 + float(y0)

    def residual(raw: np.ndarray) -> np.ndarray:
        log_ratio, c_value, log_n = raw
        predicted = predict_by_fitted_ratio(ds, shape, math.exp(log_ratio), c_value, math.exp(log_n), y0)
        return np.log(predicted) - np.log(measured)

    result = least_squares(
        residual,
        np.array([log_ratio0, c0, math.log(n0)], dtype=np.float64),
        bounds=([-60.0, -1.0e4, math.log(1.0e-6)], [60.0, 1.0e4, math.log(1.0e4)]),
        xtol=1.0e-12, ftol=1.0e-12, gtol=1.0e-12, max_nfev=20000,
    )
    ratio = math.exp(float(result.x[0]))
    c_value = float(result.x[1])
    n_value = math.exp(float(result.x[2]))
    predicted = predict_by_fitted_ratio(ds, shape, ratio, c_value, n_value, y0)
    relative = np.abs((predicted - measured) / measured)
    return {
        "ratio": ratio,
        "c": c_value,
        "n": n_value,
        "y0": float(y0),
        "sample_count": len(data),
        "mean_relative_error": float(np.mean(relative)),
        "max_relative_error": float(np.max(relative)),
        "success": bool(result.success),
        "message": str(result.message),
        "eta_sp": None,
        "k_sp": None,
        "note": "仅由试验数据识别 eta_sp/K_sp；如需拆分，运行时固定其中一个参数。",
    }


def load_long_term_data(path: str | Path) -> list[dict[str, float]]:
    """读取目标腐蚀深度预测表：target_depth_um、ds、lambda_rho。

    兼容旧格式 ``time_year,ds,lambda_rho``：旧列仅作为标签转换为
    ``target_depth_um``，不会参与断裂公式计算。
    """
    rows: list[dict[str, float]] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        label_column = "target_depth_um" if "target_depth_um" in fieldnames else "time_year"
        required = {label_column, "ds", "lambda_rho"}
        missing = required.difference(fieldnames)
        if missing:
            raise ValueError(f"长期预测数据缺少列: {', '.join(sorted(missing))}")
        for row in reader:
            if not any(str(value).strip() for value in row.values()):
                continue
            rows.append({
                "target_depth_um": float(row[label_column]),
                "ds": float(row["ds"]),
                "lambda_rho": float(row["lambda_rho"]),
            })
    if not rows:
        raise ValueError("长期预测数据至少需要一行")
    _positive("ds", [row["ds"] for row in rows])
    return rows


def predict_long_term(rows: list[dict[str, float]], result: dict[str, float | int | bool | str | None]) -> list[dict[str, float]]:
    """将拟合参数应用到长期腐蚀状态。"""
    predicted = predict_by_fitted_ratio(
        [row["ds"] for row in rows], [row["lambda_rho"] for row in rows],
        float(result["ratio"]), float(result["c"]), float(result["n"]), float(result["y0"]),
    )
    return [{**row, "fracture_strain": float(value)} for row, value in zip(rows, predicted, strict=True)]


def _write_outputs(output_dir: Path, fit: dict, experiments: list[dict], long_term: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "fracture_fitted_parameters.json").write_text(json.dumps(fit, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "fracture_fit_comparison.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample_id", "ds", "lambda_rho", "epsilon_n_f", "epsilon_pred", "relative_error"])
        writer.writeheader()
        predicted = predict_long_term(experiments, fit)  # 同一公式复算试验点，便于核对拟合误差。
        for row, fitted in zip(experiments, predicted, strict=True):
            writer.writerow({
                "sample_id": row["sample_id"],
                "ds": row["ds"],
                "lambda_rho": row["lambda_rho"],
                "epsilon_n_f": row["epsilon_n_f"],
                "epsilon_pred": fitted["fracture_strain"],
                "relative_error": abs((fitted["fracture_strain"] - row["epsilon_n_f"]) / row["epsilon_n_f"]),
            })
    with (output_dir / "long_term_fracture_strain_prediction.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["target_depth_um", "ds", "lambda_rho", "fracture_strain"])
        writer.writeheader()
        writer.writerows(long_term)


def main() -> None:
    parser = argparse.ArgumentParser(description="10组试验拟合断裂准则并预测长期断裂应变")
    parser.add_argument("--experiment", type=Path, default=Path(PATH_CONFIG["fracture_test_data"]))
    parser.add_argument("--auto-extract", action="store_true", help="先从曲线元数据和原始曲线自动提取 epsilon_n_f")
    parser.add_argument("--metadata", type=Path, default=Path(PATH_CONFIG["curve_metadata"]))
    parser.add_argument("--curves-dir", type=Path, default=Path(PATH_CONFIG["curves_dir"]))
    parser.add_argument("--gauge-length", type=float, default=None, help="位移-荷载曲线的标距")
    parser.add_argument("--drop-ratio", type=float, default=float(FRACTURE_CONFIG["curve_drop_ratio"]), help="峰值后响应下降比例，默认10%%")
    parser.add_argument("--sustain-points", type=int, default=int(FRACTURE_CONFIG["curve_sustain_points"]), help="持续下降判据的连续点数")
    parser.add_argument("--long-term", dest="long_term", type=Path, default=Path(PATH_CONFIG["long_term_corrosion_data"]))
    parser.add_argument("--output-dir", type=Path, default=Path(PATH_CONFIG["outputs"]))
    parser.add_argument("--y0", type=float, default=DEFAULT_Y0)
    parser.add_argument("--k-fixed", type=float, default=FRACTURE_CONFIG["fixed_k_sp"], help="固定 K_sp 后输出 eta_sp")
    parser.add_argument("--eta-fixed", type=float, default=FRACTURE_CONFIG["fixed_eta_sp"], help="固定 eta_sp 后输出 K_sp")
    args = parser.parse_args()
    started = time.perf_counter()
    if args.auto_extract:
        print("[1/5] 从原始拉伸曲线提取断裂应变...")
        # 与单独的第二步使用同一套判据，保证手动运行和自动运行结果一致。
        extract_from_metadata(args.metadata, args.curves_dir, args.experiment, args.gauge_length, args.drop_ratio, args.sustain_points)
    print("[2/5] 读取 10 组试验数据...")
    experiments = load_experiment_data(args.experiment)
    print(f"      已读取 {len(experiments)} 组")
    print("[3/5] 拟合 ratio、c、n...")
    fit = fit_parameters(experiments, args.y0)
    if args.k_fixed is not None:
        fit["k_sp"], fit["eta_sp"] = args.k_fixed, float(fit["ratio"]) * args.k_fixed
    elif args.eta_fixed is not None:
        fit["eta_sp"], fit["k_sp"] = args.eta_fixed, args.eta_fixed / float(fit["ratio"])
    print(f"      ratio={fit['ratio']:.10g}, c={fit['c']:.10g}, n={fit['n']:.10g}")
    print("[4/5] 读取长期腐蚀状态并预测...")
    long_term = predict_long_term(load_long_term_data(args.long_term), fit)
    _write_outputs(args.output_dir, fit, experiments, long_term)
    print(f"      已生成 {len(long_term)} 个目标腐蚀深度状态")
    print("[5/5] 保存结果完成")
    elapsed = time.perf_counter() - started
    print(f"总耗时: {elapsed:.3f} s")


if __name__ == "__main__":
    main()

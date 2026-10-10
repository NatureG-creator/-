"""第九步：拟合材料退化规律并生成目标腐蚀深度下的应力-应变曲线。

本模块使用试验数据拟合：
    fy(ds) = fy_intercept + fy_slope * ds
    fu(ds) = fu_intercept + fu_slope * ds
    E(ds)  = e_intercept  + e_slope  * ds

曲线为工程化分段曲线：弹性段 -> 线性强化段 -> 线性软化段 -> 断裂点。
它用于长期趋势预测，不替代试验标定的本构模型。
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from unified_config import FRACTURE_CONFIG, PATH_CONFIG


def _positive(name: str, values: list[float] | np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64).reshape(-1)
    if array.size == 0 or not np.all(np.isfinite(array)) or np.any(array <= 0):
        raise ValueError(f"{name} 必须是非空且全部为正的有限数值")
    return array


def _fit_line(ds: np.ndarray, values: np.ndarray) -> tuple[float, float]:
    """用 scipy 最小二乘拟合 y=a+b*ds，返回截距和斜率。"""
    def residual(parameter: np.ndarray) -> np.ndarray:
        return parameter[0] + parameter[1] * ds - values

    result = least_squares(residual, np.array([float(np.mean(values)), 0.0]), xtol=1e-12, ftol=1e-12, gtol=1e-12)
    return float(result.x[0]), float(result.x[1])


def fit_material_degradation(ds, fy, fu, modulus) -> dict[str, float | int | str]:
    """拟合 fy、fu、E 随腐蚀损伤 ds 的线性退化规律。"""
    ds_array = _positive("ds", list(ds))
    fy_array = _positive("fy", list(fy))
    fu_array = _positive("fu", list(fu))
    e_array = _positive("E", list(modulus))
    if not (ds_array.size == fy_array.size == fu_array.size == e_array.size):
        raise ValueError("ds、fy、fu、E 的数据组数必须一致")
    fy_intercept, fy_slope = _fit_line(ds_array, fy_array)
    fu_intercept, fu_slope = _fit_line(ds_array, fu_array)
    e_intercept, e_slope = _fit_line(ds_array, e_array)
    return {
        "fy_intercept": fy_intercept, "fy_slope": fy_slope,
        "fu_intercept": fu_intercept, "fu_slope": fu_slope,
        "e_intercept": e_intercept, "e_slope": e_slope,
        "sample_count": int(ds_array.size),
        "model": "linear_vs_ds",
    }


def predict_material_parameters(ds: float, fit: dict[str, float | int | str]) -> dict[str, float]:
    """根据新的 ds 预测屈服强度、抗拉强度和弹性模量。"""
    if not np.isfinite(ds) or ds < 0:
        raise ValueError("ds 必须为非负有限数值")
    fy = float(fit["fy_intercept"]) + float(fit["fy_slope"]) * float(ds)
    fu = float(fit["fu_intercept"]) + float(fit["fu_slope"]) * float(ds)
    modulus = float(fit["e_intercept"]) + float(fit["e_slope"]) * float(ds)
    if fy <= 0 or fu <= 0 or modulus <= 0:
        raise ValueError("预测得到的 fy、fu 或 E 非正，请检查 ds 范围或退化模型")
    if fu < fy:
        raise ValueError("预测得到 fu 小于 fy，请检查试验数据或退化模型")
    return {"fy": fy, "fu": fu, "E": modulus}


def build_engineering_stress_strain_curve(
    material: dict[str, float], fracture_strain: float, points: int = 501
) -> dict[str, np.ndarray]:
    """生成弹性-强化-软化工程应力应变曲线。应力单位与输入 fy/fu 一致。"""
    fy = float(material["fy"])
    fu = float(material["fu"])
    modulus = float(material["E"])
    fracture = float(fracture_strain)
    if fy <= 0 or fu <= 0 or modulus <= 0 or fracture <= 0 or points < 3:
        raise ValueError("fy、fu、E、断裂应变和 points 必须为正数")
    if fu < fy:
        raise ValueError("fu 不能小于 fy")
    yield_strain = fy / modulus
    if fracture <= yield_strain:
        raise ValueError("断裂应变必须大于屈服应变 fy/E")
    peak_strain = yield_strain + 0.4 * (fracture - yield_strain)
    strain = np.linspace(0.0, fracture, int(points), dtype=np.float64)
    stress = np.empty_like(strain)
    elastic = strain <= yield_strain
    hardening = (strain > yield_strain) & (strain <= peak_strain)
    softening = strain > peak_strain
    stress[elastic] = modulus * strain[elastic]
    stress[hardening] = fy + (fu - fy) * (strain[hardening] - yield_strain) / (peak_strain - yield_strain)
    stress[softening] = fu * (fracture - strain[softening]) / (fracture - peak_strain)
    # 离散网格未必正好包含 peak_strain，因此强制最近点落在峰值 fu，避免曲线峰值被低估。
    peak_index = int(np.argmin(np.abs(strain - peak_strain)))
    strain[peak_index] = peak_strain
    stress[peak_index] = fu
    stress[-1] = 0.0
    return {"strain": strain, "stress": stress, "yield_strain": np.array([yield_strain]), "peak_strain": np.array([peak_strain])}


def load_material_test_data(path: str | Path, min_samples: int = 10) -> list[dict[str, float | str]]:
    """读取包含 ds、fy、fu、E 的 10 组试验数据。"""
    rows: list[dict[str, float | str]] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"sample_id", "ds", "fy", "fu", "E"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"材料试验数据缺少列: {', '.join(sorted(missing))}")
        for row in reader:
            if not any(str(value).strip() for value in row.values()):
                continue
            rows.append({"sample_id": str(row["sample_id"]), "ds": float(row["ds"]), "fy": float(row["fy"]), "fu": float(row["fu"]), "E": float(row["E"])})
    if len(rows) < min_samples:
        raise ValueError(f"材料试验数据至少需要 {min_samples} 组，当前只有 {len(rows)} 组")
    return rows


def _write_curve(path: Path, curve: dict[str, np.ndarray]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["strain", "stress"])
        writer.writerows(zip(curve["strain"], curve["stress"], strict=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="拟合 fy、fu、E 退化规律并生成目标腐蚀深度下的应力-应变曲线")
    parser.add_argument("--material-data", type=Path, default=Path(PATH_CONFIG["material_test_data"]))
    parser.add_argument("--fracture-result", type=Path, default=Path(PATH_CONFIG["outputs"]) / "fracture_fitted_parameters.json")
    parser.add_argument("--long-term", type=Path, default=Path(PATH_CONFIG["long_term_corrosion_data"]))
    parser.add_argument("--output-dir", type=Path, default=Path(PATH_CONFIG["curve_outputs"]))
    parser.add_argument("--points", type=int, default=int(FRACTURE_CONFIG["curve_points"]))
    args = parser.parse_args()
    started = time.perf_counter()
    print("[1/4] 读取材料试验数据...")
    rows = load_material_test_data(args.material_data)
    fit = fit_material_degradation([r["ds"] for r in rows], [r["fy"] for r in rows], [r["fu"] for r in rows], [r["E"] for r in rows])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir.parent / "material_degradation_fit.json").write_text(json.dumps(fit, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[2/4] 材料退化规律拟合完成")
    fracture = json.loads(args.fracture_result.read_text(encoding="utf-8"))
    long_rows: list[dict[str, float]] = []
    with args.long_term.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        label_column = "target_depth_um" if "target_depth_um" in fieldnames else "time_year"
        required = {label_column, "ds", "lambda_rho"}
        missing = required.difference(fieldnames)
        if missing:
            raise ValueError(f"长期预测数据缺少列: {', '.join(sorted(missing))}")
        for row in reader:
            if any(str(value).strip() for value in row.values()):
                long_rows.append({"target_depth_um": float(row[label_column]), "ds": float(row["ds"]), "lambda_rho": float(row["lambda_rho"])})
    print(f"[3/4] 生成 {len(long_rows)} 个目标腐蚀深度状态的应力-应变曲线...")
    summary: list[dict[str, float]] = []
    for index, row in enumerate(long_rows, start=1):
        material = predict_material_parameters(row["ds"], fit)
        ratio = float(fracture["ratio"])
        c_value = float(fracture["c"])
        n_value = float(fracture["n"])
        fracture_strain = float((ratio / (row["ds"] * np.exp(float(fracture["y0"]) + c_value * row["lambda_rho"]))) ** (1.0 / n_value))
        curve = build_engineering_stress_strain_curve(material, fracture_strain, args.points)
        curve_path = args.output_dir / f"curve_{index:03d}_{row['target_depth_um']:g}um.csv"
        _write_curve(curve_path, curve)
        summary.append({**row, **material, "fracture_strain": fracture_strain, "curve_file": str(curve_path)})
        print(f"      [{index}/{len(long_rows)}] 深度={row['target_depth_um']:g} μm: fy={material['fy']:.4g}, fu={material['fu']:.4g}, E={material['E']:.4g}, epsilon={fracture_strain:.6g}")
    with (args.output_dir / "long_term_material_and_curve_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["target_depth_um", "ds", "lambda_rho", "fy", "fu", "E", "fracture_strain", "curve_file"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)
    print("[4/4] 曲线和参数保存完成")
    print(f"总耗时: {time.perf_counter() - started:.3f} s")


if __name__ == "__main__":
    main()

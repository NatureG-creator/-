"""Fit and use Zhang's corrosion-fracture criterion.

The input ``ds`` must keep one consistent scale across fitting and prediction.
When it comes from this project's fifth step, ``ds`` is the paper-style percent
value from ``(Save - Smin) / Save * 100``.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
from scipy.optimize import least_squares


DEFAULT_Y0 = 0.495


def _as_positive_1d(name: str, values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=np.float64).reshape(-1)
    if array.size == 0:
        raise ValueError(f"{name} 不能为空")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} 只能包含有限数值")
    if np.any(array <= 0):
        raise ValueError(f"{name} 必须全部为正数")
    return array


def _as_1d(name: str, values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=np.float64).reshape(-1)
    if array.size == 0:
        raise ValueError(f"{name} 不能为空")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} 只能包含有限数值")
    return array


def predict_fracture_strain(
    ds: Iterable[float],
    lambda_rho: Iterable[float],
    eta_sp: float,
    c_sp: float,
    k_sp: float,
    n_sp: float,
    y0: float = DEFAULT_Y0,
) -> np.ndarray:
    """Predict nominal fracture strain by Zhang's criterion.

    Formula:
    ``epsilon_n_f = [eta_sp / (K_sp * ds * exp(Y0 + C_sp * lambda_rho))] ** (1 / n_sp)``.
    """
    ds_array = _as_positive_1d("ds", ds)
    lambda_rho_array = _as_1d("lambda_rho", lambda_rho)
    if ds_array.shape != lambda_rho_array.shape:
        raise ValueError("ds 和 lambda_rho 长度必须一致")
    if eta_sp <= 0 or k_sp <= 0 or n_sp <= 0:
        raise ValueError("eta_sp、k_sp 和 n_sp 必须为正数")
    denominator = k_sp * ds_array * np.exp(float(y0) + float(c_sp) * lambda_rho_array)
    return (float(eta_sp) / denominator) ** (1.0 / float(n_sp))


def predict_fracture_strain_from_ratio(
    ds: Iterable[float],
    lambda_rho: Iterable[float],
    eta_over_k_sp: float,
    c_sp: float,
    n_sp: float,
    y0: float = DEFAULT_Y0,
) -> np.ndarray:
    """Predict nominal fracture strain using the identifiable eta/K ratio."""
    return predict_fracture_strain(ds, lambda_rho, eta_over_k_sp, c_sp, 1.0, n_sp, y0)


def _linear_initial_guess(ds: np.ndarray, lambda_rho: np.ndarray, epsilon_n_f: np.ndarray, y0: float) -> np.ndarray:
    """Use the log-linear form as a stable initial point for nonlinear refinement."""
    design = np.column_stack([np.ones_like(ds), np.log(ds), lambda_rho])
    coefficients, *_ = np.linalg.lstsq(design, np.log(epsilon_n_f), rcond=None)
    b0, b1, b2 = coefficients
    if b1 >= 0:
        n_sp = 2.0
        c_sp = 1.0
        log_ratio = math.log(max(np.mean(ds * epsilon_n_f**n_sp), np.finfo(float).tiny)) + y0
    else:
        n_sp = -1.0 / b1
        c_sp = b2 / b1
        log_ratio = b0 * n_sp + y0
    return np.array([log_ratio, c_sp, math.log(max(n_sp, np.finfo(float).tiny))], dtype=np.float64)


def fit_fracture_criterion_parameters(
    ds: Iterable[float],
    lambda_rho: Iterable[float],
    epsilon_n_f: Iterable[float],
    y0: float = DEFAULT_Y0,
    eta_sp_fixed: float | None = None,
    k_sp_fixed: float | None = None,
) -> dict[str, float | int | bool | str | None]:
    """Fit fracture-criterion parameters from ``ds, lambda_rho, epsilon_n_f``.

    The formula identifies ``eta_sp / K_sp``. To report separate ``eta_sp`` and
    ``K_sp``, one of them must be fixed from literature or an independent test.
    """
    ds_array = _as_positive_1d("ds", ds)
    lambda_rho_array = _as_1d("lambda_rho", lambda_rho)
    epsilon_array = _as_positive_1d("epsilon_n_f", epsilon_n_f)
    if not (ds_array.shape == lambda_rho_array.shape == epsilon_array.shape):
        raise ValueError("ds、lambda_rho 和 epsilon_n_f 长度必须一致")
    if ds_array.size < 4:
        raise ValueError("反算至少需要 4 行数据")
    if eta_sp_fixed is not None and eta_sp_fixed <= 0:
        raise ValueError("eta_sp_fixed 必须为正数")
    if k_sp_fixed is not None and k_sp_fixed <= 0:
        raise ValueError("k_sp_fixed 必须为正数")

    initial = _linear_initial_guess(ds_array, lambda_rho_array, epsilon_array, y0)

    def residual(raw: np.ndarray) -> np.ndarray:
        log_ratio, c_sp, log_n_sp = raw
        predicted = predict_fracture_strain_from_ratio(
            ds_array,
            lambda_rho_array,
            math.exp(log_ratio),
            c_sp,
            math.exp(log_n_sp),
            y0,
        )
        return np.log(predicted) - np.log(epsilon_array)

    result = least_squares(
        residual,
        initial,
        bounds=([-60.0, -1.0e4, math.log(1.0e-6)], [60.0, 1.0e4, math.log(1.0e4)]),
        xtol=1.0e-12,
        ftol=1.0e-12,
        gtol=1.0e-12,
        max_nfev=20000,
    )
    log_ratio, c_sp, log_n_sp = result.x
    eta_over_k_sp = float(math.exp(log_ratio))
    n_sp = float(math.exp(log_n_sp))

    eta_sp: float | None
    k_sp: float | None
    if eta_sp_fixed is not None and k_sp_fixed is not None:
        eta_sp = float(eta_sp_fixed)
        k_sp = float(k_sp_fixed)
        eta_over_k_sp = eta_sp / k_sp
    elif k_sp_fixed is not None:
        k_sp = float(k_sp_fixed)
        eta_sp = eta_over_k_sp * k_sp
    elif eta_sp_fixed is not None:
        eta_sp = float(eta_sp_fixed)
        k_sp = eta_sp / eta_over_k_sp
    else:
        eta_sp = None
        k_sp = None

    predicted = predict_fracture_strain_from_ratio(ds_array, lambda_rho_array, eta_over_k_sp, c_sp, n_sp, y0)
    relative_error = np.abs((predicted - epsilon_array) / epsilon_array)
    return {
        "eta_sp": eta_sp,
        "c_sp": float(c_sp),
        "k_sp": k_sp,
        "n_sp": n_sp,
        "eta_over_k_sp": eta_over_k_sp,
        "y0": float(y0),
        "sample_count": int(ds_array.size),
        "mean_relative_error": float(np.mean(relative_error)),
        "max_relative_error": float(np.max(relative_error)),
        "success": bool(result.success),
        "message": str(result.message),
        "note": "eta_sp and K_sp cannot be separated unless one of them is fixed",
    }


def load_calibration_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load a CSV with columns ``ds``, ``lambda_rho``, and ``epsilon_n_f``."""
    rows: list[tuple[float, float, float]] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"ds", "lambda_rho", "epsilon_n_f"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"拟合 CSV 缺少列: {', '.join(sorted(missing))}")
        for row in reader:
            rows.append((float(row["ds"]), float(row["lambda_rho"]), float(row["epsilon_n_f"])))
    if not rows:
        raise ValueError("拟合 CSV 至少需要一行数据")
    data = np.asarray(rows, dtype=np.float64)
    return data[:, 0], data[:, 1], data[:, 2]


def write_fit_exports(
    output_dir: str | Path,
    fit_result: dict[str, float | int | bool | str | None],
    ds: Iterable[float],
    lambda_rho: Iterable[float],
    epsilon_n_f: Iterable[float],
) -> dict[str, Path]:
    """Save fitted parameters and row-by-row prediction errors."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "fracture_fitted_parameters.json"
    csv_path = output / "fracture_fitted_parameters.csv"
    comparison_path = output / "fracture_fit_comparison.csv"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(fit_result, handle, ensure_ascii=False, indent=2, allow_nan=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fit_result.keys()))
        writer.writeheader()
        writer.writerow(fit_result)

    ds_array = _as_positive_1d("ds", ds)
    lambda_rho_array = _as_1d("lambda_rho", lambda_rho)
    epsilon_array = _as_positive_1d("epsilon_n_f", epsilon_n_f)
    predicted = predict_fracture_strain_from_ratio(
        ds_array,
        lambda_rho_array,
        float(fit_result["eta_over_k_sp"]),
        float(fit_result["c_sp"]),
        float(fit_result["n_sp"]),
        float(fit_result["y0"]),
    )
    with comparison_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["sample_id", "ds", "lambda_rho", "epsilon_n_f", "epsilon_pred", "relative_error"],
        )
        writer.writeheader()
        for i, (ds_value, lambda_value, measured, fitted) in enumerate(
            zip(ds_array, lambda_rho_array, epsilon_array, predicted, strict=True),
            start=1,
        ):
            writer.writerow(
                {
                    "sample_id": i,
                    "ds": ds_value,
                    "lambda_rho": lambda_value,
                    "epsilon_n_f": measured,
                    "epsilon_pred": fitted,
                    "relative_error": abs((fitted - measured) / measured),
                }
            )
    return {"json": json_path, "csv": csv_path, "comparison_csv": comparison_path}

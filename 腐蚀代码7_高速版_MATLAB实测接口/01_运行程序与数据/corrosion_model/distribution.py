"""MATLAB-style distribution diagnostics for corrosion samples."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import stats

from unified_config import FIGURE_CONFIG


def _matlab_bin_edges(values: np.ndarray, bin_width: float) -> np.ndarray:
    """返回 MATLAB `histogram(..., BinWidth=...)` 风格的固定柱宽边界。"""
    arr = np.asarray(values, dtype=float).reshape(-1)
    if arr.size == 0:
        raise ValueError("values must not be empty")
    width = float(bin_width)
    if width <= 0:
        raise ValueError("bin_width must be positive")
    lower = np.floor(float(np.min(arr)) / width) * width
    upper = np.ceil(float(np.max(arr)) / width) * width
    if np.isclose(lower, upper):
        upper = lower + width
    edges = np.arange(lower, upper + width * 0.5, width, dtype=float)
    if edges.size < 2:
        edges = np.array([lower, lower + width], dtype=float)
    return edges


def fenbujianyan(
    data: np.ndarray,
    *,
    output_dir: str | Path,
    filename: str = "fenbujianyan.png",
    bin_width: float = 0.1,
) -> Path:
    """Plot histogram, normal fit curve, and Q-Q plot.

    This mirrors the MATLAB helper `fenbujianyan.m`:
    - histogram(data, 'Normalization','pdf')
    - normfit / fitdist('Normal')
    - qqplot(data)

    Returns the saved PNG path.
    """

    arr = np.asarray(data, dtype=float).reshape(-1)
    if arr.size == 0:
        raise ValueError("data must not be empty")

    output_base = Path(output_dir)
    output_base.mkdir(parents=True, exist_ok=True)
    png_path = output_base / filename
    json_path = png_path.with_suffix(".json")

    mu = float(np.mean(arr))
    sigma = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial", "DejaVu Sans", "sans-serif"],
            "axes.unicode_minus": False,
        }
    )

    fig, (ax_hist, ax_qq) = plt.subplots(
        1,
        2,
        figsize=tuple(FIGURE_CONFIG["distribution_figsize"]),
        dpi=int(FIGURE_CONFIG["distribution_dpi"]),
    )

    # MATLAB `histogram(data, 'BinWidth', 0.1, 'Normalization', 'pdf')`
    # 使用固定柱宽，而不是把柱子数量固定为某个近似值。两者在数据范围
    # 不是柱宽整数倍时会产生不同的边界和柱高，进而导致图形看起来不一致。
    edges = _matlab_bin_edges(arr, bin_width)
    ax_hist.hist(arr, bins=edges, density=True, facecolor=(0.5, 0.8, 1.0), edgecolor="white")
    x = np.linspace(float(np.min(arr)), float(np.max(arr)), 400)
    if sigma > 0:
        pdf = stats.norm.pdf(x, mu, sigma)
        ax_hist.plot(x, pdf, "r-", linewidth=2)
    ax_hist.set_xlabel("数据值")
    ax_hist.set_ylabel("概率密度")
    ax_hist.set_title("数据直方图与拟合曲线")

    stats.probplot(arr, dist="norm", plot=ax_qq)
    ax_qq.set_title("Q-Q图检验正态性")

    fig.tight_layout()
    fig.savefig(png_path, bbox_inches="tight")
    plt.close(fig)

    with json_path.open("w", encoding="utf-8") as f:
        json.dump({"mu": mu, "sigma": sigma, "count": int(arr.size)}, f, ensure_ascii=False, indent=2)

    return png_path

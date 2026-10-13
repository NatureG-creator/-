"""第四步：打开可交互查看的腐蚀形貌 Figure。

功能：
- 自动读取 `腐蚀综合代码` 的 `.npz` 结果文件；
- 从 `perfect_a / a` 计算 `depth_map` 与 `baseline`；
- 弹出类似 MATLAB Figure 的窗口，可旋转、缩放、拖动查看；
- 默认生成三张论文式图：三维/二维形貌图、对数坑深分布图、改进后的径深比对数分布图；
- 三联分布图、单图和完整交互图仍可分别用 `comparison`、`single`、`full` 模式调用。

使用：
    python .\腐蚀综合代码\04_交互查看腐蚀形貌.py
    python .\腐蚀综合代码\04_交互查看腐蚀形貌.py --result .\腐蚀综合代码\step2_stage_moni_result.npz
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ==================== 在这里输入要读取的 .npz 结果文件 ====================
# 可以只写同一文件夹内的文件名，也可以改成完整绝对路径。
INPUT_RESULT_FILE = ROOT / "E:/CODEX文件/python腐蚀代码/腐蚀代码7_高速版_MATLAB实测接口/01_运行程序与数据/结果文件/step2_stage_moni_result10z.npz"

import numpy as np
from scipy.stats import norm

from corrosion_model.analysis import expand_matrix, jixiantiqu_3d, moving_avg_3d, safe_log
from corrosion_model.geometry import PaperGeometry
from corrosion_model.distribution import _matlab_bin_edges
from depth_distribution_diagnostics import (
    prepare_depth_samples, make_report, export_diagnostics,
    plot_depth_comparison, plot_single_depth_distribution,
    plot_single_ratio_distribution,
)
from unified_config import (
    FIGURE_CONFIG,
    GEOMETRY_CONFIG,
    MATLAB_CA_COMPARISON_CONFIG,
    POSTPROCESS_CONFIG,
    matlab_ca_postprocess_settings,
)


def format_elapsed_time(seconds: float) -> str:
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d} ({seconds:.2f} s)"


def configure_matplotlib() -> None:
    """配置 matplotlib，让中文标题尽量正常显示。"""
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["svg.fonttype"] = "none"


def discover_latest_result() -> Path:
    """优先读取腐蚀综合代码目录中的第二步结果。"""
    candidates = [
        ROOT / "step2_stage_moni_taichi_result.npz",
        ROOT / "step2_stage_moni_result.npz",
        ROOT / "step1_ga_taichi_result.npz",
        ROOT / "step1_ga_result.npz",
    ]
    existing = [path for path in candidates if path.exists()]
    if existing:
        return max(existing, key=lambda p: p.stat().st_mtime)
    all_results = sorted(ROOT.glob("*.npz"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not all_results:
        raise FileNotFoundError("未找到综合代码 .npz 结果文件，请先运行第一步或第二步。")
    return all_results[0]


def load_primary_state(result_path: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """从结果文件中提取最主要的三维元胞状态。

    MATLAB 对应变量：
    - `a_output` -> Python 结果文件中的 `perfect_a` 或 `a`
    - `a_sd{end}` -> Python 结果文件中的 `a_sd[-1]`
    """
    with np.load(result_path, allow_pickle=True) as npz:
        data = {key: npz[key] for key in npz.files}

    if "perfect_a" in data and np.asarray(data["perfect_a"]).ndim == 3:
        return np.asarray(data["perfect_a"], dtype=float), data
    if "a" in data and np.asarray(data["a"]).ndim == 3:
        return np.asarray(data["a"], dtype=float), data
    if "a_sd" in data:
        raw = np.asarray(data["a_sd"], dtype=object)
        if raw.ndim >= 4:
            return np.asarray(raw[-1], dtype=float), data
        if raw.size:
            return np.asarray(raw.reshape(-1)[-1], dtype=float), data
    raise KeyError("结果文件中没有识别到 `perfect_a`、`a` 或 `a_sd`，无法生成交互形貌图。")


def convert_ca_distribution_values(
    shengdu: np.ndarray,
    sjb: np.ndarray,
    space_z_um: float,
) -> tuple[np.ndarray, np.ndarray]:
    """按 MATLAB `CA.m` 的写法转换径深比和坑深数据。"""
    sjb_matlab = np.asarray(sjb, dtype=float) / float(MATLAB_CA_COMPARISON_CONFIG["sjb_divisor"])
    jsb = safe_log(1.0 / np.maximum(sjb_matlab, 1e-12))
    shengdu_log = safe_log(np.asarray(shengdu, dtype=float) * float(space_z_um))
    return jsb, shengdu_log


def compute_surface_data(
    a_state: np.ndarray,
    space: float,
    space_xy_um: float,
    window_size: int,
    expand_factor: int,
    min_prominence: float,
    min_distance: int,
    neighborhood: int | None,
    threshold: float | None,
) -> dict[str, np.ndarray | list[np.ndarray] | float]:
    """对应 MATLAB untitled.m 的后处理计算。"""
    w, l, n_plus = a_state.shape
    n = n_plus - 1
    baseline, _, _, depth_map = moving_avg_3d(a_state, window_size, w, l, n)
    baseline = expand_matrix(baseline, expand_factor)
    depth_um = (depth_map - float(np.min(depth_map))) * float(space)
    baseline_um = (baseline - float(np.min(baseline))) * float(space)

    jicha_cells = float(np.max(baseline) - np.min(baseline))
    auto_threshold, auto_neighborhood = matlab_ca_postprocess_settings(jicha_cells)
    effective_threshold = auto_threshold if threshold is None else float(threshold)
    effective_neighborhood = auto_neighborhood if neighborhood is None else int(neighborhood)
    params = {
        "MinProminence": min_prominence,
        "MinDistance": min_distance,
        "Neighborhood": (effective_neighborhood, effective_neighborhood),
    }
    shengdu, sjb, zhijin, max_locs, min_locs, boundaries, boundary_coords = jixiantiqu_3d(
        baseline, n, params, effective_threshold
    )
    jsb, shengdu_log = convert_ca_distribution_values(shengdu, sjb, space)
    # X/Y 与 Z 方向尺寸分开传入，避免把 X/Y 尺寸当作函数外部变量引用。
    geometry = PaperGeometry(space_xy_um=space_xy_um, space_z_um=space)

    quality_loss = float((w * l * n - np.sum(a_state == 1)) / (w * l * n))
    average_depth = quality_loss * n * float(space)

    return {
        "baseline": baseline,
        "depth_map": depth_map,
        "baseline_um": baseline_um,
        "depth_um": depth_um,
        "shengdu_log": shengdu_log,
        # 原始指未经对数处理的提取结果；仍包含原 pit_metrics 的 +1 层口径。
        "pit_depth_cells": np.asarray(shengdu, dtype=float),
        "pit_depth_um": np.asarray(shengdu, dtype=float) * float(space),
        "pit_diameter_cells": np.asarray(zhijin, dtype=float),
        "jsb": jsb,
        "max_locs": max_locs,
        "min_locs": min_locs,
        "boundaries": boundaries,
        "boundary_coords": boundary_coords,
        "average_depth": average_depth,
        "bj_depth": float(np.mean(depth_um)),
        "jicha": float(jicha_cells * space),
        "jicha_cells": jicha_cells,
        "effective_neighborhood": float(effective_neighborhood),
        "effective_threshold": float(effective_threshold),
    }


def add_click_value_tool(ax, values: np.ndarray, x_grid: np.ndarray, y_grid: np.ndarray) -> None:
    """给二维等高线图添加点击读数功能，近似 MATLAB 数据光标。"""
    annotation = ax.annotate(
        "",
        xy=(0, 0),
        xytext=(18, 18),
        textcoords="offset points",
        bbox=dict(boxstyle="round", fc="white", ec="0.4", alpha=0.92),
        arrowprops=dict(arrowstyle="->", color="0.25"),
    )
    annotation.set_visible(False)

    def on_click(event):
        if event.inaxes != ax or event.xdata is None or event.ydata is None:
            return
        col = int(np.argmin(np.abs(x_grid[0, :] - event.xdata)))
        row = int(np.argmin(np.abs(y_grid[:, 0] - event.ydata)))
        val = float(values[row, col])
        annotation.xy = (x_grid[row, col], y_grid[row, col])
        annotation.set_text(f"X {x_grid[row, col]:.0f}\nY {y_grid[row, col]:.0f}\nLevel {val:.4f}")
        annotation.set_visible(True)
        event.canvas.draw_idle()

    ax.figure.canvas.mpl_connect("button_press_event", on_click)


def plot_surface_and_contour(
    surface_um: np.ndarray,
    max_locs: np.ndarray,
    space: float,
    title: str,
    *,
    figsize: tuple[float, float] | None = None,
    dpi: int | None = None,
    cmap: str | None = None,
) -> None:
    """打开 3D 曲面 + 二维等高线交互窗口。"""
    import matplotlib.pyplot as plt

    rows, cols = surface_um.shape
    x = np.arange(cols) * float(space)
    y = np.arange(rows) * float(space)
    x_grid, y_grid = np.meshgrid(x, y)

    fig = plt.figure(
        figsize=figsize or tuple(FIGURE_CONFIG["interactive_figsize"]),
        dpi=int(dpi or FIGURE_CONFIG["interactive_dpi"]),
    )
    ax3d = fig.add_subplot(1, 2, 1, projection="3d")
    surf = ax3d.plot_surface(
        x_grid,
        y_grid,
        surface_um,
        cmap=cmap or str(FIGURE_CONFIG["surface_cmap"]),
        linewidth=float(FIGURE_CONFIG["surface_linewidth"]),
        antialiased=bool(FIGURE_CONFIG["surface_antialiased"]),
    )
    ax3d.set_title("三维曲面极值点检测")
    ax3d.set_xlabel("X方向/μm")
    ax3d.set_ylabel("Y方向/μm")
    ax3d.set_zlabel("腐蚀深度/μm")
    if max_locs.size:
        rows0 = max_locs[:, 0].astype(int) - 1
        cols0 = max_locs[:, 1].astype(int) - 1
        valid = (rows0 >= 0) & (rows0 < rows) & (cols0 >= 0) & (cols0 < cols)
        rows0 = rows0[valid]
        cols0 = cols0[valid]
        ax3d.scatter(cols0 * space, rows0 * space, surface_um[rows0, cols0], c="red", s=36, label="极大值点")
        ax3d.legend(loc="upper right")
    fig.colorbar(surf, ax=ax3d, shrink=0.72, pad=0.08, label="腐蚀深度/μm")

    ax2d = fig.add_subplot(1, 2, 2)
    plot_cmap = cmap or str(FIGURE_CONFIG["surface_cmap"])
    contour = ax2d.contourf(x_grid, y_grid, surface_um, levels=24, cmap=plot_cmap)
    ax2d.contour(x_grid, y_grid, surface_um, levels=24, colors="k", linewidths=0.45)
    if max_locs.size:
        ax2d.scatter(cols0 * space, rows0 * space, marker="x", c="red", s=50, linewidths=2, label="极大值点")
    ax2d.set_title("二维等高线极值点")
    ax2d.set_xlabel("X方向/μm")
    ax2d.set_ylabel("Y方向/μm")
    ax2d.set_aspect("equal", adjustable="box")
    ax2d.legend(loc="upper right")
    fig.colorbar(contour, ax=ax2d, shrink=0.72, pad=0.05, label="腐蚀深度/μm")
    add_click_value_tool(ax2d, surface_um, x_grid, y_grid)
    ax3d.view_init(
        elev=float(FIGURE_CONFIG["surface_elev"]),
        azim=float(FIGURE_CONFIG["surface_azim"]),
    )

    fig.suptitle(title)
    fig.tight_layout()
    return fig


def plot_distribution(
    values: np.ndarray,
    title: str,
    *,
    figsize: tuple[float, float] | None = None,
    dpi: int | None = None,
    xlabel: str = "数据值",
    bin_width: float | None = None,
) -> None:
    """打开直方图 + 正态拟合曲线窗口。"""
    import matplotlib.pyplot as plt

    values = np.asarray(values, dtype=float).reshape(-1)
    values = values[np.isfinite(values)]
    if values.size == 0:
        print(f"{title}: 没有可绘制数据")
        return

    mu = float(np.mean(values))
    sigma = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
    fig, ax = plt.subplots(
        figsize=figsize or tuple(FIGURE_CONFIG["distribution_figsize"]),
        dpi=int(dpi or FIGURE_CONFIG["distribution_dpi"]),
    )
    bins = _matlab_bin_edges(values, float(MATLAB_CA_COMPARISON_CONFIG["hist_bin_width"] if bin_width is None else bin_width))
    ax.hist(values, bins=bins, density=True, color="#9fd0f0", edgecolor="black", alpha=0.8, label="数据分布")
    if sigma > 0:
        xs = np.linspace(float(np.min(values)), float(np.max(values)), 240)
        ax.plot(xs, norm.pdf(xs, mu, sigma), "r-", linewidth=2.5, label="拟合正态曲线")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("概率密度")
    ax.grid(True, alpha=0.2)
    ax.legend()
    fig.tight_layout()


def main(argv: list[str] | None = None) -> int:
    start_time = time.perf_counter()
    parser = argparse.ArgumentParser(description="打开类似 MATLAB Figure 的交互式腐蚀形貌查看窗口")
    parser.add_argument(
        "--result",
        default=str(INPUT_RESULT_FILE),
        help="指定 .npz 结果文件；默认读取文件开头的 INPUT_RESULT_FILE",
    )
    parser.add_argument("--space-z", type=float, default=float(GEOMETRY_CONFIG["space_z_um"]), help="论文元胞 Z 向尺寸，单位 μm")
    parser.add_argument("--space-xy", type=float, default=float(GEOMETRY_CONFIG["space_xy_um"]), help="论文元胞 X/Y 向尺寸，单位 μm")
    parser.add_argument("--window-size", type=int, default=int(POSTPROCESS_CONFIG["interactive_window_size"]), help="moving_avg_3d 平滑窗口，对应 MATLAB 的 5")
    parser.add_argument("--expand-factor", type=int, default=int(POSTPROCESS_CONFIG["expand_factor"]), help="expandMatrix 放大倍数，对应 MATLAB 的 N")
    # 第四步对应 MATLAB `郭\\untitled.m`，不是 CA.m 的 GA 后处理参数。
    parser.add_argument("--min-prominence", type=float, default=float(POSTPROCESS_CONFIG["min_prominence"]), help="极值点 MinProminence")
    parser.add_argument("--min-distance", type=int, default=int(POSTPROCESS_CONFIG["min_distance"]), help="极值点 MinDistance")
    parser.add_argument("--neighborhood", type=int, default=int(POSTPROCESS_CONFIG["neighborhood"]), help="极值点 Neighborhood 的边长")
    parser.add_argument("--threshold", type=float, default=float(POSTPROCESS_CONFIG["watershed_threshold"]), help="分水岭边界阈值，对应 MATLAB yuzhi")
    parser.add_argument("--log-normalization", type=float, default=float(POSTPROCESS_CONFIG["log_normalization"]), help="正数 C，对数归一化因子，只缩放横坐标")
    parser.add_argument("--hist-bin-width", type=float, default=float(MATLAB_CA_COMPARISON_CONFIG["hist_bin_width"]), help="对数及归一化对数图的柱宽")
    parser.add_argument("--raw-bin-width-um", type=float, default=None, help="原始坑深图的柱宽，单位 μm；留空自动分箱")
    parser.add_argument(
        "--plot-mode",
        choices=("paper", "single", "comparison", "full"),
        default="paper",
        help="paper：三张论文式图（默认）；single：只画坑深图；comparison：三联图；full：三联图加 3D 和等高线",
    )
    parser.add_argument("--output-dir", default=str(ROOT / "outputs" / "depth_distribution_diagnostics"), help="诊断图、CSV、JSON 保存目录，每个结果文件使用独立子目录")
    parser.add_argument("--no-show", action="store_true", help="保存分布诊断图和数据，不弹出交互窗口")
    args = parser.parse_args(argv)

    result_path = Path(args.result) if args.result else discover_latest_result()
    print("=== 第四步开始：交互式腐蚀形貌查看 ===")
    print(f"读取结果文件: {result_path}")
    print(f"元胞尺寸: {args.space_xy} x {args.space_xy} x {args.space_z} μm")

    a_state, data = load_primary_state(result_path)
    stats = compute_surface_data(
        a_state=a_state,
        space=args.space_z,
        space_xy_um=args.space_xy,
        window_size=args.window_size,
        expand_factor=args.expand_factor,
        min_prominence=args.min_prominence,
        min_distance=args.min_distance,
        neighborhood=args.neighborhood,
        threshold=args.threshold,
    )

    samples = prepare_depth_samples(stats['pit_depth_cells'],args.space_z,args.log_normalization)
    boundary_fallback_count = sum(np.asarray(coords).size == 0 for coords in stats['boundary_coords'])
    report = make_report(samples,dict(
        source_npz=str(result_path.resolve()),source_type='CA/导入的三维元胞结果',
        surface_shape=list(a_state.shape),window_size=args.window_size,
        gaussian_sigma=float(POSTPROCESS_CONFIG['gaussian_sigma']),
        min_prominence=args.min_prominence,min_distance=args.min_distance,
        neighborhood=int(stats['effective_neighborhood']),threshold=stats['effective_threshold'],
        log_bin_width=args.hist_bin_width,raw_bin_width_um=args.raw_bin_width_um,
        boundary_fallback_count=boundary_fallback_count,
        pit_depth_definition='原提取算法：非空边界坑 (baseline_at_max-min(baseline)+1)*space_z_um；空边界默认 1 层',
    ))
    print(f"识别坑数={report['extracted_count']}，有效正深度样本={report['valid_count']}，无效样本={report['invalid_count']}")
    print(f"空边界默认值坑数={boundary_fallback_count}；这些属于原提取算法的回退值，不能视为已核实的真实坑深。")
    print(f"对数柱宽={args.hist_bin_width}，原始深度柱宽={args.raw_bin_width_um or '自动'} μm，归一化因子 C={args.log_normalization}")
    for key,label in [('raw_depth_um','H / μm'),('log_depth','ln(H / 1 μm)'),('normalized_log_depth','ln(H / 1 μm) / C')]:
        summary = report[key]
        print(f"{label}: n={summary['count']}, 均值={summary['mean']}, 标准差={summary['std']}; {summary['normality_note']}")
    print('C 只缩放对数值，不能增加坑数或使非正态分布变成正态。')

    if args.no_show:
        import matplotlib
        matplotlib.use('Agg')
    configure_matplotlib()
    output_dir = Path(args.output_dir) / result_path.stem
    csv_path,json_path = export_diagnostics(samples,report,output_dir)
    figure = None
    comparison = None
    surface_figure = None
    ratio_figure = None
    if args.plot_mode == "paper":
        surface_figure = plot_surface_and_contour(
            surface_um=np.asarray(stats["baseline_um"], dtype=float),
            max_locs=np.asarray(stats["max_locs"], dtype=int),
            space=args.space_xy,
            title=result_path.stem,
        )
        surface_figure.savefig(output_dir/'surface_and_contour.png', dpi=int(FIGURE_CONFIG['interactive_dpi']))
        surface_figure.savefig(output_dir/'surface_and_contour.pdf')
        surface_figure.savefig(output_dir/'surface_and_contour.svg')

        figure = plot_single_depth_distribution(
            samples,
            log_bin_width=args.hist_bin_width,
            dpi=int(FIGURE_CONFIG['distribution_dpi']),
        )
        figure.savefig(output_dir/'pit_depth_distribution.png', dpi=int(FIGURE_CONFIG['distribution_dpi']))
        figure.savefig(output_dir/'pit_depth_distribution.pdf')
        figure.savefig(output_dir/'pit_depth_distribution.svg')

        ratio_figure = plot_single_ratio_distribution(
            np.asarray(stats['jsb'], dtype=float),
            bin_width=args.hist_bin_width,
            dpi=int(FIGURE_CONFIG['distribution_dpi']),
        )
        ratio_figure.savefig(output_dir/'ratio_distribution.png', dpi=int(FIGURE_CONFIG['distribution_dpi']))
        ratio_figure.savefig(output_dir/'ratio_distribution.pdf')
        ratio_figure.savefig(output_dir/'ratio_distribution.svg')
        print(f'三张论文式图已保存到: {output_dir}')
    elif args.plot_mode == "single":
        figure = plot_single_depth_distribution(
            samples,
            log_bin_width=args.hist_bin_width,
            dpi=int(FIGURE_CONFIG['distribution_dpi']),
        )
        figure.savefig(output_dir/'pit_depth_distribution.png', dpi=int(FIGURE_CONFIG['distribution_dpi']))
        figure.savefig(output_dir/'pit_depth_distribution.pdf')
        figure.savefig(output_dir/'pit_depth_distribution.svg')
        print(f'单张腐蚀坑深度分布图已保存到: {output_dir / "pit_depth_distribution.png"}')
    else:
        comparison = plot_depth_comparison(
            samples,
            log_bin_width=args.hist_bin_width,
            raw_bin_width_um=args.raw_bin_width_um,
            dpi=int(FIGURE_CONFIG['distribution_dpi']),
        )
        comparison.savefig(output_dir/'pit_depth_comparison.png', dpi=int(FIGURE_CONFIG['distribution_dpi']))
        comparison.savefig(output_dir/'pit_depth_comparison.pdf')
        comparison.savefig(output_dir/'pit_depth_comparison.svg')
        print(f'三联分布诊断图已保存到: {output_dir / "pit_depth_comparison.png"}')
    print(f'分布诊断已保存到: {output_dir}')

    print(f"平均腐蚀深度 Average_depth = {stats['average_depth']:.6g} μm")
    print(f"不均匀腐蚀深度 jicha = {stats['jicha']:.6g} μm ({stats['jicha_cells']:.6g} 个元胞层)")
    print(f"MATLAB 对齐参数: Neighborhood={int(stats['effective_neighborhood'])}, yuzhi={stats['effective_threshold']:.3g}")
    print(f"边界/平均深度 bj_depth = {stats['bj_depth']:.6g} μm")
    if "perfect_result_sd" in data:
        perfect_result = np.asarray(data["perfect_result_sd"], dtype=float).reshape(-1)
        if perfect_result.size >= 4:
            wucha = 0.1 * perfect_result[0] + 0.3 * perfect_result[1] + 0.2 * perfect_result[2] + 0.4 * perfect_result[3]
            print(f"加权误差 wucha = {wucha:.6g}")

    import matplotlib.pyplot as plt
    if not args.no_show:
        if args.plot_mode == "paper":
            print("已打开三张论文式图：形貌图、坑深分布图和径深比对数分布图。")
        elif args.plot_mode == "full":
            title = result_path.stem
            plot_surface_and_contour(
                surface_um=np.asarray(stats["baseline_um"], dtype=float),
                max_locs=np.asarray(stats["max_locs"], dtype=int),
                space=args.space_xy,
                title=title,
            )
            plot_distribution(
                np.asarray(stats["jsb"], dtype=float),
                "径深比对数转换量：数据分布与参考正态拟合",
                xlabel="ln(1 / (sjb / 缩放因子))",
                bin_width=args.hist_bin_width,
            )
            print("已打开完整交互窗口：3D 图可旋转，等高线图可点击读数。")
        elif args.plot_mode == "comparison":
            print("已打开三联分布图：第一幅为原始坑深标准图，另外两幅对数分布图保留。")
        else:
            print("已打开单张原始腐蚀坑深度直方图和正态拟合曲线。")
        plt.show()
    else:
        if figure is not None:
            plt.close(figure)
        if comparison is not None:
            plt.close(comparison)
        if surface_figure is not None:
            plt.close(surface_figure)
        if ratio_figure is not None:
            plt.close(ratio_figure)

    elapsed = time.perf_counter() - start_time
    print(f"第四步交互查看总耗时: {format_elapsed_time(elapsed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

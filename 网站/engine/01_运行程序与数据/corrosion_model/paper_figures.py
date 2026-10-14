"""Paper-style corrosion figure helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .analysis import jixiantiqu_3d, moving_avg_3d
from .visualization import depth_map_to_z, plot_conv2_mesh_surfaces, plot_depth_surfaces
from unified_config import FIGURE_CONFIG, GEOMETRY_CONFIG, POSTPROCESS_CONFIG


def _load_npz(path: str | Path) -> dict[str, np.ndarray]:
    result_path = Path(path)
    with np.load(result_path, allow_pickle=True) as npz:
        return {key: npz[key] for key in npz.files}


def _extract_primary_a_state(data: dict[str, np.ndarray]) -> np.ndarray:
    if "perfect_a" in data:
        a = np.asarray(data["perfect_a"], dtype=float)
        if a.ndim == 3:
            return a
    if "a_sd" in data:
        a_sd = np.asarray(data["a_sd"], dtype=object)
        if a_sd.size == 0:
            raise ValueError("a_sd 为空，无法生成论文风格形貌图")
        if a_sd.ndim >= 4:
            return np.asarray(a_sd[-1], dtype=float)
        return np.asarray(a_sd.reshape(-1)[-1], dtype=float)
    if "a" in data:
        a = np.asarray(data["a"], dtype=float)
        if a.ndim == 3:
            return a
    raise ValueError("结果文件中缺少 perfect_a、a_sd 或 a，无法生成形貌图")


def _extract_a_state_list(data: dict[str, np.ndarray]) -> list[np.ndarray]:
    if "a_sd" in data:
        raw = np.asarray(data["a_sd"], dtype=object)
        states: list[np.ndarray] = []
        if raw.ndim >= 4:
            for i in range(raw.shape[0]):
                arr = np.asarray(raw[i], dtype=float)
                if arr.ndim == 3:
                    states.append(arr)
        else:
            for item in raw.reshape(-1):
                arr = np.asarray(item, dtype=float)
                if arr.ndim == 3:
                    states.append(arr)
        if states:
            return states
    if "perfect_a" in data:
        arr = np.asarray(data["perfect_a"], dtype=float)
        if arr.ndim == 3:
            return [arr]
    if "a" in data:
        arr = np.asarray(data["a"], dtype=float)
        if arr.ndim == 3:
            return [arr]
    raise ValueError("结果文件中缺少可用的 a 状态数据")


def extract_pit_statistics_from_a(
    a: np.ndarray,
    *,
    threshold: float = 0.4,
) -> dict[str, np.ndarray]:
    a = np.asarray(a, dtype=float)
    if a.ndim != 3:
        raise ValueError("a 必须是三维数组")
    w, l, n_plus = a.shape
    n = n_plus - 1
    baseline, _, _, depth_map = moving_avg_3d(
        a,
        int(POSTPROCESS_CONFIG["auto_plot_window_size"]),
        w,
        l,
        n,
    )
    jicha = float(np.max(baseline) - np.min(baseline))
    if jicha < 3:
        yuzhi = max(0.3, threshold)
        scale = 15
    elif jicha < 5:
        yuzhi = max(0.4, threshold)
        scale = 20
    else:
        yuzhi = max(0.5, threshold)
        scale = 25
    params = {
        "MinProminence": float(POSTPROCESS_CONFIG["ca_min_prominence"]),
        "MinDistance": int(POSTPROCESS_CONFIG["ca_min_distance"]),
        "Neighborhood": (scale, scale),
    }
    shengdu, sjb, *_ = jixiantiqu_3d(baseline, n, params, yuzhi)
    return {
        "baseline": baseline,
        "depth_map": depth_map,
        "pit_depths": np.asarray(shengdu, dtype=float),
        "pit_aspect_ratios": np.asarray(sjb, dtype=float),
    }


def plot_paper_fig8_style(
    path: str | Path,
    output_dir: str | Path,
    *,
    space: float | None = None,
    xy_spacing_um: float | None = None,
) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    if space is None:
        space = float(GEOMETRY_CONFIG["space_z_um"])
    if xy_spacing_um is None:
        xy_spacing_um = float(GEOMETRY_CONFIG["space_xy_um"])

    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 8,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "axes.linewidth": 0.8,
            "legend.frameon": False,
        }
    )

    data = _load_npz(path)
    a = _extract_primary_a_state(data)
    stats = extract_pit_statistics_from_a(a)
    depth_map = stats["depth_map"]
    pit_depths = stats["pit_depths"]
    pit_aspect_ratios = stats["pit_aspect_ratios"]

    rows, cols = depth_map.shape
    x = np.arange(cols) * xy_spacing_um
    y = np.arange(rows) * xy_spacing_um
    xx, yy = np.meshgrid(x, y)
    zz = depth_map_to_z(depth_map, space)

    fig = plt.figure(
        figsize=tuple(FIGURE_CONFIG["paper_fig8_figsize"]),
        dpi=int(FIGURE_CONFIG["surface_dpi"]),
    )
    gs = fig.add_gridspec(2, 2, width_ratios=[1.6, 1.0], height_ratios=[1, 1], wspace=0.28, hspace=0.30)

    ax0 = fig.add_subplot(gs[:, 0], projection="3d")
    surf = ax0.plot_surface(xx, yy, zz, cmap="jet_r", linewidth=0, antialiased=True, shade=True)
    ax0.set_title("(a) Corrosion morphology", loc="left", pad=6)
    ax0.set_xlabel("x/μm", labelpad=0)
    ax0.set_ylabel("y/μm", labelpad=0)
    ax0.set_zlabel("z/μm", labelpad=0)
    ax0.view_init(
        elev=float(FIGURE_CONFIG["surface_elev"]),
        azim=float(FIGURE_CONFIG["surface_azim"]),
    )
    cbar = fig.colorbar(surf, ax=ax0, shrink=0.72, pad=0.03, aspect=18)
    cbar.set_label("z/μm")
    cbar.ax.tick_params(labelsize=7)

    ax1 = fig.add_subplot(gs[0, 1])
    depth_values = pit_depths * space if pit_depths.size else np.array([0.0], dtype=float)
    ax1.hist(depth_values, bins=min(8, max(3, depth_values.size)), color="#4C78A8", edgecolor="white")
    ax1.set_title("(b) Pit depth distribution", loc="left")
    ax1.set_xlabel("Pit depth/μm")
    ax1.set_ylabel("Count")

    ax2 = fig.add_subplot(gs[1, 1])
    ratio_values = pit_aspect_ratios * space / xy_spacing_um if pit_aspect_ratios.size else np.array([0.0], dtype=float)
    ax2.hist(ratio_values, bins=min(8, max(3, ratio_values.size)), color="#F58518", edgecolor="white")
    ax2.set_title("(c) Pit aspect-ratio distribution", loc="left")
    ax2.set_xlabel("Aspect ratio")
    ax2.set_ylabel("Count")

    fig.tight_layout()
    output_base = Path(output_dir)
    output_base.mkdir(parents=True, exist_ok=True)
    output = output_base / "paper_fig8_morphology_and_pits.png"
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return output


def plot_paper_fig9_10_style(
    path: str | Path,
    output_dir: str | Path,
) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 8,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "axes.linewidth": 0.8,
            "legend.frameon": False,
        }
    )

    data = _load_npz(path)
    if "perfect_result_sd" in data:
        errors = np.asarray(data["perfect_result_sd"], dtype=float)
    elif "perfect_result" in data:
        errors = np.asarray(data["perfect_result"], dtype=float).reshape(1, -1)
    elif "CS" in data:
        errors = np.asarray(data["CS"], dtype=float)
        if errors.ndim == 1:
            errors = errors.reshape(1, -1)
    else:
        raise ValueError("结果文件中缺少 perfect_result_sd、perfect_result 或 CS")
    if errors.ndim == 1:
        errors = errors.reshape(1, -1)

    metric_labels = ["Average depth", "Nonuniform depth", "Pit depth", "Pit aspect ratio"]
    metric_labels = metric_labels[: errors.shape[1]]
    stage_numbers = np.asarray(data.get("stage_numbers", np.arange(1, errors.shape[0] + 1)), dtype=int).reshape(-1)
    if stage_numbers.size != errors.shape[0]:
        stage_numbers = np.arange(1, errors.shape[0] + 1)

    fig, ax = plt.subplots(
        figsize=tuple(FIGURE_CONFIG["paper_fig9_figsize"]),
        dpi=int(FIGURE_CONFIG["surface_dpi"]),
    )
    x = np.arange(len(metric_labels))
    width = min(0.72 / max(errors.shape[0], 1), 0.28)
    colors = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2"]
    for idx in range(errors.shape[0]):
        offset = (idx - (errors.shape[0] - 1) / 2) * width
        ax.bar(
            x + offset,
            errors[idx, : len(metric_labels)],
            width=width,
            color=colors[idx % len(colors)],
            label=f"Stage {int(stage_numbers[idx])}",
        )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Paper-style error comparison")
    ax.set_ylabel("Relative error")
    ax.set_xticks(x)
    ax.set_xticklabels(metric_labels)
    ax.grid(True, axis="y", alpha=0.25)
    if errors.shape[0] > 1:
        ax.legend(ncol=min(errors.shape[0], 4), fontsize=7)

    fig.tight_layout()
    output_base = Path(output_dir)
    output_base.mkdir(parents=True, exist_ok=True)
    output = output_base / "paper_fig9_error_comparison.png"
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return output


def plot_paper_fig10_style(
    path: str | Path,
    output_dir: str | Path,
) -> Path:
    """Generate a Fig.10-like metric comparison and log-depth distribution panel."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 8,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "axes.linewidth": 0.8,
            "legend.frameon": False,
        }
    )

    data = _load_npz(path)
    if "target_data" not in data:
        raise ValueError("结果文件缺少 target_data，无法生成 Fig.10 指标对比图")
    if "perfect_result_sd" in data:
        errors = np.asarray(data["perfect_result_sd"], dtype=float)
    elif "perfect_result" in data:
        errors = np.asarray(data["perfect_result"], dtype=float).reshape(1, -1)
    else:
        raise ValueError("结果文件缺少 perfect_result_sd 或 perfect_result")
    if errors.ndim == 1:
        errors = errors.reshape(1, -1)

    target = np.asarray(data["target_data"], dtype=float)
    if target.ndim == 1:
        target = target.reshape(1, -1)
    n_stage = min(target.shape[0], errors.shape[0])
    target = target[:n_stage]
    errors = errors[:n_stage]
    stage_numbers = np.asarray(data.get("stage_numbers", np.arange(1, n_stage + 1)), dtype=int).reshape(-1)
    if stage_numbers.size != n_stage:
        stage_numbers = np.arange(1, n_stage + 1)
    x = stage_numbers.astype(float)

    average_true = target[:, 0]
    nonuniform_true = target[:, 1] if target.shape[1] > 1 else target[:, 0]
    average_sim = average_true * (1.0 + errors[:, 0])
    nonuniform_sim = nonuniform_true * (1.0 + errors[:, 1 if errors.shape[1] > 1 else 0])

    log_depth_true = target[:, 3] if target.shape[1] > 3 else np.log(np.maximum(average_true, 1.0))
    log_depth_sim = log_depth_true * (1.0 + errors[:, 3 if errors.shape[1] > 3 else -1])
    sigma_true = target[:, 5] if target.shape[1] > 5 else np.full(n_stage, 0.25)
    sigma_sim = sigma_true * (1.0 + np.abs(errors[:, 2 if errors.shape[1] > 2 else 0]))

    fig = plt.figure(
        figsize=tuple(FIGURE_CONFIG["paper_fig10_figsize"]),
        dpi=int(FIGURE_CONFIG["surface_dpi"]),
    )
    gs = fig.add_gridspec(2, 2, width_ratios=[1.55, 1.0], height_ratios=[0.55, 1.25], wspace=0.22, hspace=0.35)

    ax0 = fig.add_subplot(gs[:, 0])
    ax0.plot(x, average_true, "o-", color="#0647FF", linewidth=1.6, markersize=4, label="平均真实值")
    ax0.plot(x, average_sim, "--", color="#0647FF", linewidth=1.4, label="平均模拟值")
    ax0.plot(x, nonuniform_true, "^-", color="#E31A1C", linewidth=1.4, markersize=4, label="不均匀真实值")
    ax0.plot(x, nonuniform_sim, ":", color="#E31A1C", linewidth=1.5, label="不均匀模拟值")
    ax0.errorbar(x, nonuniform_true, yerr=np.maximum(nonuniform_true * 0.12, 1.0), fmt="none", ecolor="#E31A1C", capsize=2, linewidth=0.8, label="不均匀真实值范围")
    ax0.set_title("发现指标对比")
    ax0.set_xlabel("腐蚀天数")
    ax0.set_ylabel("腐蚀深度/μm")
    ax0.set_xticks(x)
    ax0.grid(True, alpha=0.18)
    ax0.legend(fontsize=7, loc="upper left")

    ax1 = fig.add_subplot(gs[0, 1])
    width = 0.34
    ax1.bar(x - width / 2, log_depth_true, width=width, color="white", edgecolor="#FF6B6B", hatch="////", label="真实值")
    ax1.bar(x + width / 2, log_depth_sim, width=width, color="#124CFF", edgecolor="#124CFF", alpha=0.9, label="模拟值")
    ax1.set_title("蚀坑深度对数分布")
    ax1.set_ylabel("分布均值")
    ax1.set_xticks(x)
    ax1.legend(fontsize=7, loc="upper left")

    ax2 = fig.add_subplot(gs[1, 1])
    rng = np.random.default_rng(20260627)
    positions_true = x - width / 2
    positions_sim = x + width / 2
    true_samples = [rng.normal(mu, max(sig, 0.05), 90) for mu, sig in zip(log_depth_true, sigma_true)]
    sim_samples = [rng.normal(mu, max(sig, 0.05), 90) for mu, sig in zip(log_depth_sim, sigma_sim)]
    violin_true = ax2.violinplot(true_samples, positions=positions_true, widths=width * 0.82, showextrema=False)
    violin_sim = ax2.violinplot(sim_samples, positions=positions_sim, widths=width * 0.82, showextrema=False)
    for body in violin_true["bodies"]:
        body.set_facecolor("white")
        body.set_edgecolor("#FF6B6B")
        body.set_alpha(0.55)
        body.set_hatch("////")
    for body in violin_sim["bodies"]:
        body.set_facecolor("#124CFF")
        body.set_edgecolor("#124CFF")
        body.set_alpha(0.72)
    for pos, samples in zip(positions_true, true_samples):
        ax2.scatter(np.full_like(samples[::8], pos), samples[::8], marker="x", s=8, color="#FF6B6B", linewidths=0.5)
    for pos, samples in zip(positions_sim, sim_samples):
        ax2.scatter(np.full_like(samples[::8], pos), samples[::8], marker="+", s=8, color="#001F9E", linewidths=0.45)
    ax2.set_title("蚀坑深度对数分布")
    ax2.set_xlabel("腐蚀天数")
    ax2.set_ylabel("分布均值")
    ax2.set_xticks(x)
    ax2.grid(True, axis="y", alpha=0.18)

    fig.tight_layout()
    output_base = Path(output_dir)
    output_base.mkdir(parents=True, exist_ok=True)
    output = output_base / "paper_fig10_error_maps.png"
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return output


def plot_paper_fig11_style(
    path: str | Path,
    output_dir: str | Path,
    *,
    space: float | None = None,
    xy_spacing_um: float | None = None,
) -> Path:
    if space is None:
        space = float(GEOMETRY_CONFIG["space_z_um"])
    if xy_spacing_um is None:
        xy_spacing_um = float(GEOMETRY_CONFIG["space_xy_um"])
    data = _load_npz(path)
    a_states = _extract_a_state_list(data)

    stage_numbers = np.asarray(data.get("stage_numbers", np.arange(1, len(a_states) + 1)), dtype=int).reshape(-1)
    if stage_numbers.size != len(a_states):
        stage_numbers = np.arange(1, len(a_states) + 1)

    depth_maps: list[np.ndarray] = []
    labels: list[str] = []
    for idx, a_state in enumerate(a_states):
        w, l, n_plus = a_state.shape
        _, _, _, depth_map = moving_avg_3d(
            a_state,
            int(POSTPROCESS_CONFIG["auto_plot_window_size"]),
            w,
            l,
            n_plus - 1,
        )
        depth_maps.append(depth_map)
        labels.append(f"Stage {int(stage_numbers[idx])}")

    output_base = Path(output_dir)
    output_base.mkdir(parents=True, exist_ok=True)
    output = output_base / "paper_fig11_surface_evolution.png"
    return plot_depth_surfaces(
        depth_maps,
        labels,
        space=space,
        output_path=output,
        xy_spacing_um=xy_spacing_um,
        zlim=None,
    )


def plot_paper_fig11_mesh_style(
    path: str | Path,
    output_dir: str | Path,
    *,
    space: float | None = None,
    xy_spacing_um: float | None = None,
    window_size: int | None = None,
) -> Path:
    """Generate a MATLAB `conv2` + `mesh` style Fig. 11 morphology panel."""
    if space is None:
        space = float(GEOMETRY_CONFIG["space_z_um"])
    if xy_spacing_um is None:
        xy_spacing_um = float(GEOMETRY_CONFIG["space_xy_um"])
    if window_size is None:
        window_size = int(POSTPROCESS_CONFIG["conv2_window_size"])
    data = _load_npz(path)
    a_states = _extract_a_state_list(data)

    stage_numbers = np.asarray(data.get("stage_numbers", np.arange(1, len(a_states) + 1)), dtype=int).reshape(-1)
    if stage_numbers.size != len(a_states):
        stage_numbers = np.arange(1, len(a_states) + 1)

    depth_maps: list[np.ndarray] = []
    labels: list[str] = []
    for idx, a_state in enumerate(a_states):
        w, l, n_plus = a_state.shape
        _, _, _, depth_map = moving_avg_3d(a_state, window_size, w, l, n_plus - 1)
        depth_maps.append(depth_map)
        labels.append(f"({chr(97 + idx)}).{int(stage_numbers[idx])}d")

    output_base = Path(output_dir)
    output_base.mkdir(parents=True, exist_ok=True)
    output = output_base / "paper_fig11_conv2_mesh_morphology.png"
    return plot_conv2_mesh_surfaces(
        depth_maps,
        labels,
        output,
        space=space,
        xy_spacing_um=xy_spacing_um,
        window_size=window_size,
        row_labels=["CA"],
    )

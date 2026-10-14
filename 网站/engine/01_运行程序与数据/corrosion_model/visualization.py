"""Visualization helpers for corrosion depth surfaces."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from unified_config import FIGURE_CONFIG, GEOMETRY_CONFIG, POSTPROCESS_CONFIG


def _convolve_2d_nearest(depth: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Use SciPy when available; otherwise provide a small NumPy fallback."""
    try:
        from scipy import ndimage  # type: ignore

        return ndimage.convolve(depth, kernel, mode="nearest")
    except Exception:
        pad_y = kernel.shape[0] // 2
        pad_x = kernel.shape[1] // 2
        padded = np.pad(depth, ((pad_y, pad_y), (pad_x, pad_x)), mode="edge")
        out = np.zeros_like(depth, dtype=np.float64)
        for y in range(depth.shape[0]):
            for x in range(depth.shape[1]):
                window = padded[y : y + kernel.shape[0], x : x + kernel.shape[1]]
                out[y, x] = float(np.sum(window * kernel))
        return out


def conv2_smooth_depth_map(depth_map: np.ndarray, window_size: int | None = None) -> np.ndarray:
    """MATLAB `conv2(data, kernel, 'same')` equivalent for depth smoothing."""
    if window_size is None:
        window_size = int(POSTPROCESS_CONFIG["conv2_window_size"])
    if window_size <= 0:
        raise ValueError("window_size 必须为正整数")
    depth = np.asarray(depth_map, dtype=np.float64)
    kernel = np.ones((window_size, window_size), dtype=np.float64) / float(window_size**2)
    return _convolve_2d_nearest(depth, kernel)


def depth_map_to_z(depth_map: np.ndarray, space: float, reference_layer: float | None = None) -> np.ndarray:
    """Convert MATLAB-style depth layers to a negative z-depth surface in μm.

    可调项：`depth_map`、`space`、`reference_layer`。
    """
    depth_map = np.asarray(depth_map, dtype=np.float64)
    if reference_layer is None:
        reference_layer = float(np.min(depth_map))
    return -(depth_map - reference_layer) * float(space)


def plot_depth_surfaces(
    depth_maps: list[np.ndarray],
    labels: list[str],
    space: float,
    output_path: str | Path,
    xy_spacing_um: float | None = None,
    cmap: str | None = None,
    zlim: tuple[float, float] | None = None,
) -> Path:
    """Plot a 3xN grid of corrosion depth surfaces like paper figures.

    可调项：`depth_maps`、`labels`、`space`、`output_path`、`xy_spacing_um`、
    `cmap`、`zlim`。
    """
    import matplotlib.pyplot as plt
    from matplotlib import cm

    if xy_spacing_um is None:
        xy_spacing_um = float(GEOMETRY_CONFIG["space_xy_um"])
    if cmap is None:
        cmap = str(FIGURE_CONFIG["surface_cmap"])
    if len(depth_maps) != len(labels):
        raise ValueError("depth_maps 和 labels 数量必须一致")
    n_items = len(depth_maps)
    ncols = 3
    nrows = int(np.ceil(n_items / ncols))
    z_surfaces = [depth_map_to_z(depth_map, space) for depth_map in depth_maps]
    if zlim is None:
        z_min = min(float(np.min(z)) for z in z_surfaces)
        zlim = (min(z_min, -0.05), 0.0)

    panel_width, panel_height = FIGURE_CONFIG["surface_panel_size"]
    fig = plt.figure(
        figsize=(float(panel_width) * ncols, float(panel_height) * nrows),
        dpi=int(FIGURE_CONFIG["surface_dpi"]),
    )
    norm = plt.Normalize(vmin=zlim[0], vmax=zlim[1])
    cmap_obj = plt.get_cmap(cmap)

    for idx, (z, label) in enumerate(zip(z_surfaces, labels), start=1):
        rows, cols = z.shape
        x = (np.arange(cols) - cols / 2.0) * xy_spacing_um
        y = (np.arange(rows) - rows / 2.0) * xy_spacing_um
        xx, yy = np.meshgrid(x, y)
        ax = fig.add_subplot(nrows, ncols, idx, projection="3d")
        ax.plot_surface(
            xx,
            yy,
            z,
            rstride=1,
            cstride=1,
            facecolors=cmap_obj(norm(z)),
            linewidth=0,
            antialiased=bool(FIGURE_CONFIG["surface_antialiased"]),
            shade=True,
        )
        ax.set_title(f"({label})", loc="left", fontsize=11, pad=0)
        ax.set_xlabel("x/μm", labelpad=-2)
        ax.set_ylabel("y/μm", labelpad=-2)
        ax.set_zlabel("z/μm", labelpad=-4)
        ax.set_zlim(*zlim)
        ax.view_init(
            elev=float(FIGURE_CONFIG["surface_elev"]),
            azim=float(FIGURE_CONFIG["surface_azim"]),
        )
        ax.tick_params(axis="both", labelsize=8, pad=-2)
        ax.tick_params(axis="z", labelsize=8, pad=-1)
        mappable = cm.ScalarMappable(norm=norm, cmap=cmap_obj)
        mappable.set_array(z)
        cbar = fig.colorbar(mappable, ax=ax, shrink=0.72, pad=0.02, aspect=18)
        cbar.ax.tick_params(labelsize=8)

    for empty_idx in range(n_items + 1, nrows * ncols + 1):
        ax = fig.add_subplot(nrows, ncols, empty_idx)
        ax.axis("off")

    fig.tight_layout()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return output


def plot_conv2_mesh_surfaces(
    depth_maps: list[np.ndarray],
    labels: list[str],
    output_path: str | Path,
    *,
    space: float | None = None,
    xy_spacing_um: float | None = None,
    window_size: int | None = None,
    row_labels: list[str] | None = None,
    cmap: str | None = None,
) -> Path:
    """Plot Fig.11-like multi-panel mesh/surface corrosion morphology."""
    import matplotlib.pyplot as plt
    from matplotlib import cm

    if space is None:
        space = float(GEOMETRY_CONFIG["space_z_um"])
    if xy_spacing_um is None:
        xy_spacing_um = float(GEOMETRY_CONFIG["space_xy_um"])
    if window_size is None:
        window_size = int(POSTPROCESS_CONFIG["conv2_window_size"])
    if cmap is None:
        cmap = str(FIGURE_CONFIG["mesh_cmap"])
    if len(depth_maps) != len(labels):
        raise ValueError("depth_maps 和 labels 数量必须一致")
    if not depth_maps:
        raise ValueError("depth_maps 不能为空")

    ncols = len(depth_maps)
    nrows = 1 if row_labels is None else max(1, len(row_labels))
    panel_width, panel_height = FIGURE_CONFIG["mesh_panel_size"]
    fig = plt.figure(
        figsize=(float(panel_width) * ncols, float(panel_height) * nrows + 0.45),
        dpi=int(FIGURE_CONFIG["mesh_dpi"]),
    )
    cmap_obj = plt.get_cmap(cmap)
    row_labels = row_labels or [""]

    smoothed_um = [
        (conv2_smooth_depth_map(depth_map, window_size) - float(np.min(depth_map))) * float(space)
        for depth_map in depth_maps
    ]
    z_min = min(float(np.min(z)) for z in smoothed_um)
    z_max = max(float(np.max(z)) for z in smoothed_um)
    if np.isclose(z_min, z_max):
        z_max = z_min + 1.0

    for row_idx in range(nrows):
        for col_idx, (z, label) in enumerate(zip(smoothed_um, labels), start=1):
            rows, cols = z.shape
            x = np.arange(rows, dtype=float) * float(xy_spacing_um)
            y = np.arange(cols, dtype=float) * float(xy_spacing_um)
            xx, yy = np.meshgrid(y, x)
            ax = fig.add_subplot(nrows, ncols, row_idx * ncols + col_idx, projection="3d")
            ax.plot_surface(
                xx,
                yy,
                z,
                rstride=1,
                cstride=1,
                cmap=cmap_obj,
                linewidth=float(FIGURE_CONFIG["surface_linewidth"] or 0.15),
                edgecolor=(0.25, 0.25, 0.25, 0.22),
                antialiased=bool(FIGURE_CONFIG["surface_antialiased"]),
                shade=True,
                vmin=z_min,
                vmax=z_max,
            )
            ax.set_xlabel("y/μm", labelpad=-6)
            ax.set_ylabel("x/μm", labelpad=-6)
            ax.set_zlabel("z/μm", labelpad=-8)
            ax.set_zlim(z_min, z_max)
            ax.set_title(label, y=-0.18, fontsize=8)
            ax.view_init(
                elev=float(FIGURE_CONFIG["surface_elev"]),
                azim=float(FIGURE_CONFIG["surface_azim"]),
            )
            ax.tick_params(axis="both", labelsize=6, pad=-4)
            ax.tick_params(axis="z", labelsize=6, pad=-3)
            ax.xaxis.pane.set_alpha(0.0)
            ax.yaxis.pane.set_alpha(0.0)
            ax.zaxis.pane.set_alpha(0.0)
        if row_labels[row_idx]:
            fig.text(0.015, 0.67 - row_idx * 0.42, row_labels[row_idx], fontsize=10, va="center")

    norm = plt.Normalize(vmin=z_min, vmax=z_max)
    mappable = cm.ScalarMappable(norm=norm, cmap=cmap_obj)
    mappable.set_array(np.array([z_min, z_max]))
    cbar = fig.colorbar(mappable, ax=fig.axes, orientation="horizontal", shrink=0.82, pad=0.08, aspect=45)
    cbar.set_label("Corrosion depth/μm", fontsize=8)
    cbar.ax.tick_params(labelsize=7)

    fig.suptitle("Cellular automaton simulation morphology diagram", y=0.98, fontsize=11)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return output

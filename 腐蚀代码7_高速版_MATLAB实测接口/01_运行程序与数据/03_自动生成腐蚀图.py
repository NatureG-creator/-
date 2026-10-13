"""第三步：自动读取结果文件并出图。

功能目标：
- 自动读取 `腐蚀综合代码` 的 `.npz` 结果
- 生成参数图、误差图、分布检验图、腐蚀形貌图

MATLAB / Python 语法差异提示：
- MATLAB 常直接在脚本里画图，Python 更常把“读取”和“绘图”拆开
- Python 这里先统一读 `.npz`，再按字段决定绘哪些图
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime_bootstrap import ensure_taichi_runtime

ensure_taichi_runtime()

import numpy as np

from corrosion_model.analysis import moving_avg_3d
from corrosion_model.distribution import fenbujianyan
from corrosion_model.visualization import plot_depth_surfaces
from unified_config import (
    FIGURE_CONFIG,
    GEOMETRY_CONFIG,
    MATLAB_CA_COMPARISON_CONFIG,
    PATH_CONFIG,
    POSTPROCESS_CONFIG,
    matlab_ca_postprocess_settings,
)


PARAMETER_NAMES = [
    "p_uniform_base",
    "p_passive_base",
    "p_break",
    "CL_threshold",
    "alpha_corrosion",
    "simutive_point",
    "alpha_p_break",
    "p_h",
    "p_v",
    "p_o",
]

ERROR_NAMES_4 = ["Average_depth", "bj_depth", "jsb_mean", "shengdu_mix"]
ERROR_NAMES_6 = ["Average_depth", "bj_depth", "jsb_mean", "shengdu_mean", "sigma1", "sigma2"]


def format_elapsed_time(seconds: float) -> str:
    """把秒数格式化成 `时:分:秒`，方便看完整代码耗时。"""
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d} ({seconds:.2f} s)"


def discover_result_files(search_dir: str | Path = ROOT) -> list[Path]:
    """发现可能的结果文件。

    只扫描腐蚀综合代码目录及其 outputs，避免误读其他版本的结果。
    """
    base = Path(search_dir)
    candidates: list[Path] = []
    search_roots = [base, base / "outputs"]
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.glob("*.npz"):
            if any(part in {".venv", "__pycache__"} for part in path.parts):
                continue
            candidates.append(path)
    return sorted(set(candidates), key=lambda p: p.stat().st_mtime, reverse=True)


def _as_2d(array: np.ndarray) -> np.ndarray:
    values = np.asarray(array, dtype=float)
    if values.ndim == 1:
        values = values.reshape(1, -1)
    return values


def _stage_labels(data: dict[str, np.ndarray], n_rows: int) -> list[str]:
    stages = data.get("stage_numbers")
    if stages is None:
        return [f"Stage {i + 1}" for i in range(n_rows)]
    stages = np.asarray(stages).reshape(-1)
    if stages.size != n_rows:
        return [f"Stage {i + 1}" for i in range(n_rows)]
    return [f"Stage {int(stage)}" for stage in stages]


def _save_parameter_heatmap(parameters: np.ndarray, labels: list[str], output_path: Path, show: bool) -> Path:
    import matplotlib.pyplot as plt

    base_width, base_height = FIGURE_CONFIG["parameter_heatmap_figsize"]
    fig, ax = plt.subplots(
        figsize=(float(base_width), max(float(base_height), 0.6 * len(labels) + 2)),
        dpi=int(FIGURE_CONFIG["auto_plot_dpi"]),
    )
    image = ax.imshow(parameters, aspect="auto", cmap="viridis")
    ax.set_title("腐蚀综合代码：最优参数热图")
    ax.set_xlabel("CA 参数")
    ax.set_ylabel("阶段")
    ax.set_xticks(np.arange(len(PARAMETER_NAMES)))
    ax.set_xticklabels(PARAMETER_NAMES, rotation=35, ha="right")
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels)
    for i in range(parameters.shape[0]):
        for j in range(parameters.shape[1]):
            ax.text(j, i, f"{parameters[i, j]:.3g}", ha="center", va="center", color="white", fontsize=7)
    fig.colorbar(image, ax=ax, shrink=0.86, label="parameter value")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)
    return output_path


def _save_parameter_lines(parameters: np.ndarray, labels: list[str], output_path: Path, show: bool) -> Path:
    import matplotlib.pyplot as plt

    x = np.arange(parameters.shape[0])
    fig, ax = plt.subplots(
        figsize=tuple(FIGURE_CONFIG["parameter_line_figsize"]),
        dpi=int(FIGURE_CONFIG["auto_plot_dpi"]),
    )
    for idx, name in enumerate(PARAMETER_NAMES[: parameters.shape[1]]):
        ax.plot(x, parameters[:, idx], marker="o", linewidth=1.5, label=name)
    ax.set_title("腐蚀综合代码：阶段最优参数变化")
    ax.set_xlabel("阶段")
    ax.set_ylabel("parameter value")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.grid(True, alpha=0.25)
    ax.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)
    return output_path


def _save_error_bars(errors: np.ndarray, labels: list[str], output_path: Path, show: bool) -> Path:
    import matplotlib.pyplot as plt

    names = ERROR_NAMES_6 if errors.shape[1] == 6 else ERROR_NAMES_4[: errors.shape[1]]
    x = np.arange(errors.shape[0])
    width = min(0.8 / max(errors.shape[1], 1), 0.18)
    fig, ax = plt.subplots(
        figsize=tuple(FIGURE_CONFIG["error_bar_figsize"]),
        dpi=int(FIGURE_CONFIG["auto_plot_dpi"]),
    )
    for idx, name in enumerate(names):
        offset = (idx - (len(names) - 1) / 2) * width
        ax.bar(x + offset, errors[:, idx], width=width, label=name)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("腐蚀综合代码：最优个体相对误差")
    ax.set_xlabel("阶段")
    ax.set_ylabel("relative error")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)
    return output_path


def _save_depth_heatmap(depth_map: np.ndarray, output_path: Path, show: bool, space_z: float, space_xy: float) -> Path:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(
        figsize=tuple(FIGURE_CONFIG["auto_heatmap_figsize"]),
        dpi=int(FIGURE_CONFIG["auto_plot_dpi"]),
    )
    rows, cols = depth_map.shape
    depth_um = (np.asarray(depth_map, dtype=float) - float(np.min(depth_map))) * float(space_z)
    extent = [0.0, cols * float(space_xy), rows * float(space_xy), 0.0]
    image = ax.imshow(depth_um, cmap="jet", origin="upper", extent=extent, aspect="auto")
    ax.set_title("腐蚀综合代码：腐蚀深度图")
    ax.set_xlabel("x/μm")
    ax.set_ylabel("y/μm")
    fig.colorbar(image, ax=ax, shrink=0.86, label="depth/μm")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)
    return output_path


def _candidate_depth_maps(data: dict[str, np.ndarray], space: float) -> list[tuple[str, np.ndarray]]:
    depth_maps: list[tuple[str, np.ndarray]] = []
    for key in ("depth_map", "baseline"):
        if key in data:
            values = np.asarray(data[key], dtype=float)
            if values.ndim == 2:
                depth_maps.append((key, values))
            elif values.ndim == 3:
                for i in range(values.shape[0]):
                    depth_maps.append((f"{key}_{i + 1}", values[i]))
    if "a" in data:
        a = np.asarray(data["a"])
        if a.ndim == 3:
            w, l, n_plus = a.shape
            _, _, _, depth_map = moving_avg_3d(
                a,
                int(POSTPROCESS_CONFIG["auto_plot_window_size"]),
                w,
                l,
                n_plus - 1,
            )
            depth_maps.append(("from_a", depth_map))
    return depth_maps


def plot_result_file(
    path: str | Path,
    output_dir: str | Path | None = None,
    show: bool = False,
    space_z: float | None = None,
    space_xy: float | None = None,
) -> list[Path]:
    if space_z is None:
        space_z = float(GEOMETRY_CONFIG["space_z_um"])
    if space_xy is None:
        space_xy = float(GEOMETRY_CONFIG["space_xy_um"])
    result_path = Path(path)
    output_base = Path(output_dir) if output_dir is not None else Path(PATH_CONFIG["auto_plots"])
    stem = result_path.stem
    written: list[Path] = []
    with np.load(result_path, allow_pickle=True) as npz:
        data = {key: npz[key] for key in npz.files}

    if "perfect_parameter_sd" in data:
        parameters = _as_2d(data["perfect_parameter_sd"])
    elif "perfect_parameter" in data:
        parameters = _as_2d(data["perfect_parameter"])
    else:
        parameters = np.empty((0, 0), dtype=float)

    if parameters.size:
        labels = _stage_labels(data, parameters.shape[0])
        written.append(_save_parameter_heatmap(parameters, labels, output_base / f"{stem}_parameters_heatmap.png", show))
        written.append(_save_parameter_lines(parameters, labels, output_base / f"{stem}_parameters_lines.png", show))

    if "perfect_result_sd" in data:
        errors = _as_2d(data["perfect_result_sd"])
    elif "perfect_result" in data:
        errors = _as_2d(data["perfect_result"])
    elif "CS" in data:
        errors = _as_2d(data["CS"])
    else:
        errors = np.empty((0, 0), dtype=float)

    if errors.size:
        labels = _stage_labels(data, errors.shape[0])
        written.append(_save_error_bars(errors, labels, output_base / f"{stem}_errors.png", show))

    depth_maps = _candidate_depth_maps(data, space_z)
    for name, depth_map in depth_maps:
        written.append(_save_depth_heatmap(depth_map, output_base / f"{stem}_{name}_heatmap.png", show, space_z, space_xy))
    if depth_maps:
        labels = [name for name, _ in depth_maps]
        maps = [depth_map for _, depth_map in depth_maps]
        written.append(plot_depth_surfaces(maps, labels, space_z, output_base / f"{stem}_depth_surfaces.png", xy_spacing_um=space_xy))

    # 第三步：如果结果文件里保存了腐蚀形貌状态，就顺手补充分布检验图。
    if "a_sd" in data or "perfect_a" in data or "a" in data:
        try:
            primary_a = None
            if "perfect_a" in data:
                arr = np.asarray(data["perfect_a"], dtype=float)
                if arr.ndim == 3:
                    primary_a = arr
            if primary_a is None and "a_sd" in data:
                raw = np.asarray(data["a_sd"], dtype=object)
                if raw.ndim >= 4:
                    primary_a = np.asarray(raw[-1], dtype=float)
                elif raw.size:
                    primary_a = np.asarray(raw.reshape(-1)[-1], dtype=float)
            if primary_a is None and "a" in data:
                arr = np.asarray(data["a"], dtype=float)
                if arr.ndim == 3:
                    primary_a = arr

            if primary_a is not None and primary_a.ndim == 3:
                w, l, n_plus = primary_a.shape
                _, _, _, depth_map = moving_avg_3d(
                    primary_a,
                    int(POSTPROCESS_CONFIG["auto_plot_window_size"]),
                    w,
                    l,
                    n_plus - 1,
                )
                baseline = np.asarray(depth_map, dtype=float)
                jicha = float(np.max(baseline) - np.min(baseline))
                yuzhi, scale = matlab_ca_postprocess_settings(jicha)
                from corrosion_model.analysis import jixiantiqu_3d, safe_log

                params = {
                    "MinProminence": float(MATLAB_CA_COMPARISON_CONFIG["min_prominence"]),
                    "MinDistance": int(MATLAB_CA_COMPARISON_CONFIG["min_distance"]),
                    "Neighborhood": (
                        int(scale),
                        int(scale),
                    ),
                }
                shengdu, sjb, *_ = jixiantiqu_3d(baseline, n_plus - 1, params, yuzhi)
                # MATLAB CA.m 明确先做 `sjb = sjb ./ 10`，再计算
                # `jsb = log(1 ./ sjb)`；这里不能改成 space_z/space_xy。
                sjb_matlab = sjb / float(MATLAB_CA_COMPARISON_CONFIG["sjb_divisor"])
                jsb = safe_log(1.0 / np.maximum(sjb_matlab, 1e-12))
                shengdu_log = safe_log(np.maximum(shengdu * space_z, 1e-12))
                written.append(
                    fenbujianyan(jsb, output_dir=output_base, filename=f"{stem}_jsb_distribution.png")
                )
                written.append(
                    fenbujianyan(
                        shengdu_log / float(MATLAB_CA_COMPARISON_CONFIG["depth_log_normalization"]),
                        output_dir=output_base,
                        filename=f"{stem}_shengdu_distribution.png",
                    )
                )
        except Exception as exc:
            print(f"分布检验图生成失败: {exc}")

    return written


def plot_many(
    paths: Iterable[str | Path],
    output_dir: str | Path | None = None,
    show: bool = False,
    space_z: float | None = None,
    space_xy: float | None = None,
) -> list[Path]:
    written: list[Path] = []
    path_list = list(paths)
    total = len(path_list)
    for index, path in enumerate(path_list, start=1):
        print(f"[第三步/出图] 正在处理第 {index}/{total} 个结果文件: {Path(path)}")
        written.extend(plot_result_file(path, output_dir=output_dir, show=show, space_z=space_z, space_xy=space_xy))
        print(f"[第三步/出图] 第 {index}/{total} 个结果文件处理完成")
    return written


def main(argv: list[str] | None = None) -> int:
    start_time = time.perf_counter()  # Time 函数：记录脚本开始时间，用于计算总耗时。
    parser = argparse.ArgumentParser(description="自动读取腐蚀综合代码结果并出图")
    parser.add_argument("results", nargs="*", help="可选：指定一个或多个 .npz 结果文件")
    parser.add_argument("--search-dir", default=str(ROOT), help="未指定结果文件时的搜索目录")
    parser.add_argument("--output-dir", default=str(PATH_CONFIG["auto_plots"]), help="图片输出目录")
    parser.add_argument("--space-z", type=float, default=float(GEOMETRY_CONFIG["space_z_um"]), help="论文元胞 Z 向尺寸，单位 μm")
    parser.add_argument("--space-xy", type=float, default=float(GEOMETRY_CONFIG["space_xy_um"]), help="论文元胞 X/Y 向尺寸，单位 μm")
    parser.add_argument("--show", action="store_true", help="保存图片后同时弹窗显示")
    args = parser.parse_args(argv)

    print("=== 第三步开始：自动出图 ===")
    print(f"搜索目录: {args.search_dir}")
    print(f"输出目录: {args.output_dir}")
    print(f"元胞尺寸: {args.space_xy} x {args.space_xy} x {args.space_z} μm")
    paths = [
        Path(r"E:\CODEX文件\python腐蚀代码\00000腐蚀综合代码\结果文件\step2_stage_moni_result1.npz")
    ]
    print(f"发现结果文件数量: {len(paths)}")
    if not paths:
        print("未找到 .npz 结果文件。请先运行 01_运行单阶段GA.py 或 02_运行多阶段stage_moni.py。")
        elapsed = time.perf_counter() - start_time
        print(f"第三步总耗时: {format_elapsed_time(elapsed)}")
        return 1

    written = plot_many(paths, output_dir=args.output_dir, show=args.show, space_z=args.space_z, space_xy=args.space_xy)
    if not written:
        print("找到结果文件，但没有识别到可出图字段。支持 perfect_parameter_sd、perfect_result_sd、CS、depth_map、baseline、a。")
        elapsed = time.perf_counter() - start_time
        print(f"第三步总耗时: {format_elapsed_time(elapsed)}")
        return 1

    print("已生成图片：")
    for path in written:
        print(f"- {path}")
    elapsed = time.perf_counter() - start_time
    print(f"第三步总耗时: {format_elapsed_time(elapsed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

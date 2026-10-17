"""00000 腐蚀综合代码的统一参数中心。

只修改本文件中的参数，其他入口程序会自动读取。

单位约定：
- 几何尺寸统一使用 μm；
- `target_data` 第一列为目标平均腐蚀深度，单位 μm；
- 应力、弹性模量等材料单位沿用输入试验数据，不在此处强制换算。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent


# ==================== 1. 物理尺寸参数 ====================
# w/l/n 是元胞数量；space_xy_um 和 space_z_um 是单个元胞的物理尺寸。
GEOMETRY_CONFIG = {
    "grid_w": 200,
    "grid_l": 80,
    "grid_n": 100,
    "space_xy_um": 25,        # X/Y 元胞尺寸：25 μm；100 格对应 2500 μm。
    "space_z_um": 25,         # Z 向元胞尺寸：25 μm；100 层对应 2500 μm 的 CA 计算域。
    "plate_thickness_um": 6000.0,  # 原始钢板厚度 t：6000 μm。
}


# ==================== 2. 目标腐蚀数据 ====================
# 高速版目标来源开关："matlab" 自动读取 matlab_target.mat；"manual" 读取下方手动数据。
# 默认保持 MATLAB 自动模式；手动模式仍要求输入原高速版的六列原始统计量。
TARGET_SOURCE = "matlab"

# ==================== 2.1 多工况目标清单 ====================
# 将 enabled 改为 True 后，主程序按 cases 中的 mode 分配顺序组和并行组。
# 每个工况的结果、进度记录和日志都会写入“结果文件/<case_name>/”，不会互相覆盖。
# 当前几何网格为 100×100×100；并行时仍需根据内存调小 parallel_case_workers 或内部 workers。
MULTI_CASE_CONFIG = {
    "enabled": True,
    # 运行方式：single=只跑一个，sequential=多组依次跑，parallel=多组同时跑，mixed=兼容旧的分组模式。
    "run_mode": "single",
    # 旧版分组开关仅在 run_mode="mixed" 时使用，保留以兼容旧配置。
    "sequential_enabled": False,
    "parallel_enabled": True,

    # 并行组同时运行的工况数；每个工况内部仍使用 STAGE_GA_CONFIG 的 workers。
    "parallel_case_workers": 6,
    "cases": [
        {
            "case_name": "C17_100d_z",
            "matlab_target": str(ROOT.parent / "实测目标" / "20261012z100d" / "matlab_target.mat"),
        },
        # {
        #     "case_name": "C17_100d_f",
        #     "matlab_target": r"E:\CODEX文件\python腐蚀代码\腐蚀代码7_高速版_MATLAB实测接口\实测目标\C17_100d_f\matlab_target.mat",
        #     "mode": "parallel",
        # },
    ],
}

# 原始 02_运行多阶段stage_moni.py 使用的目标数据，列顺序必须保持不变：
# [平均腐蚀深度, 不均匀腐蚀深度, 深径比指标, 坑深分布指标, sigma1, sigma2]
ACTIVE_STAGE_TARGET_DATA = np.array(
    [[697.0, 262.0, 2.00, 5.79, 0.63, 0.23]],
    dtype=float,
)

# 第一步单阶段 GA 的原有示例数据单独保留，避免与第二步目标数据混用。
SINGLE_STAGE_TARGET_DATA = np.array(
    [456.0, 100.0, 1.86, 5.74, 0.63, 0.27],
    dtype=float,
)


# ==================== 3. GA 参数 ====================
# 原始多阶段 02 的参数：F=2000、种群 301、选择 10、最大代数 101。
STAGE_GA_CONFIG = {
    "F": 2000,
    "nind": 301,
    "selected_count": 10,
    "maxgen": 101,
    "parallel_workers": 10,
}

# 第一步保留原入口中的快速示例设置。
SINGLE_STAGE_GA_CONFIG = {
    "F": 200,
    "nind": 10,
    "selected_count": 4,
    "maxgen": 3,
    "parallel_workers": 8,
}

GA_CONFIG = {
    "bits_per_param": 11,
    "base_px": 0.5,
    "base_pm": 0.5,
    "decay_rate": 0.2,
    "sigma_share": 0.3,
    "seed": 1,
                # *****************************************************************************************************************
}

GA_PARAMETER_LOWER_BOUNDS = np.array(
    [0.0, 0.0, 0.0, 5.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0],
    dtype=float,
)
GA_PARAMETER_UPPER_BOUNDS = np.array(
    [0.3, 1.0, 0.005, 35.0, 35.0, 0.1, 35.0, 0.5, 0.5, 15.0],
    dtype=float,
)


# ==================== 4. CA 参数 ====================
CA_CONFIG = {
    "alpha_passive": 0.8,
    "initial_d": 3.0,
    "initial_cl": 0.0,
    "initial_enhancement_steps": 0,
    "initial_enhancement_beta": 1.0,
    "convex_height_limit": 30.0,
}


# ==================== 5. Taichi 参数 ====================
TAICHI_CONFIG = {
    "use_taichi": True,          # 高速版入口也读取此开关。
    "arch": "cpu",              # cpu 或 gpu。
    "allow_taichi_parallel": True,  # 是否同时启用 Taichi 和进程池。
    "verbose": True,             # 高速版阶段、代数和个体进度输出。
}


# ==================== 6. 腐蚀形貌后处理参数 ====================
POSTPROCESS_CONFIG = {
    "gaussian_sigma": 2.0,           # moving_avg_3d 内部高斯滤波强度,高斯滤波强度。越大，表面越平滑，噪声和小坑越容易消失；越小，细节更多，但伪极值可能增多。。
    "interactive_window_size": 7,    # 交互形貌图平滑窗口,。越大，交互曲面越顺滑，但小腐蚀坑会被削弱。建议使用奇数，如 5 或 7。。
    "auto_plot_window_size": 15,     # 自动出图使用的平滑窗口,越大，自动生成的表面越平缓。。
    "conv2_window_size": 15,         # mesh/conv2 图的二维均值卷积窗口,控制网格曲面的顺滑程度。。
    "expand_factor": 1,               # expandMatrix 放大倍数；不是真正平滑,矩阵放大倍数。1 表示不放大；2 表示每个点扩展成 2×2。它不是平滑。。
    "min_prominence": 0.001,            # 极值点突出程度,越大，只保留明显的大坑；越小，识别更多小坑和噪声点。。
    "min_distance": 15,               # 两个腐蚀坑中心的最小网格距离。越大，附近腐蚀坑更容易被合并；越小，识别的坑更多。
    "neighborhood": 12,               # 判断局部极值时的邻域边长。越大，识别大尺度腐蚀坑；越小，识别更多局部小坑。
    "watershed_threshold": 0.3,       # 分水岭区域边界阈值。影响腐蚀坑边界、面积和等效直径。。
    "log_normalization": 1.04,        # MATLAB 分布图中的对数归一化因子,只影响分布检验横坐标和拟合参数，不改变原始坑深。。
    "ca_min_prominence": 0.05,        # CA 适应度后处理中的极值突出程度,CA 自适应后处理使用的极值突出程度，通常比交互分析更灵敏。。
    "ca_min_distance": 15,            # CA 适应度后处理中的极值最小间距,CA 自适应后处理中腐蚀坑中心的最小距离。。
}


# ==================== 6.1 MATLAB CA 分布对齐参数 ====================
# 仅用于对齐 MATLAB `CA.m` 的分布指标和 `fenbujianyan.m` 的直方图。
# 不修改 CA 元胞更新规则；它只决定平滑后表面的极值提取、对数换算和画柱宽。
MATLAB_CA_COMPARISON_CONFIG = {
    "min_prominence": 0.05,           # MATLAB CA.m: MinProminence = 0.05。
    "min_distance": 15,               # MATLAB CA.m: MinDistance = 15。
    "dynamic_neighborhood": True,     # 根据 jicha 选择 15/20/25。
    "threshold_by_jicha": True,       # 根据 jicha 选择分水岭阈值 0.3/0.4/0.5。
    "sjb_divisor": 10.0,              # MATLAB CA.m: sjb = sjb ./ 10。
    "depth_log_scale": "space_z",    # MATLAB CA.m: log(shengdu .* space)。
    "depth_log_normalization": 1.0,   # MATLAB CA.m 没有除以 1.04。
    "hist_bin_width": 0.1,            # MATLAB fenbujianyan.m: BinWidth = 0.1,直方图柱宽。
}


def matlab_ca_postprocess_settings(jicha: float) -> tuple[float, int]:
    """返回 MATLAB CA.m 对应的 `(yuzhi, scale)`。

    `jicha` 是平滑后基准面的极差，单位仍是元胞层数，不能先乘 μm。
    """
    if not MATLAB_CA_COMPARISON_CONFIG["threshold_by_jicha"]:
        return 0.3, 15
    if float(jicha) < 3.0:
        return 0.3, 15
    if float(jicha) < 5.0:
        return 0.4, 20
    return 0.5, 25


# ==================== 7. 出图画面参数 ====================
# figsize 单位为英寸；dpi 越大，保存图片越清晰、文件越大。
FIGURE_CONFIG = {
    "interactive_figsize": (14.0, 6.8),
    "interactive_dpi": 160,
    "distribution_figsize": (7.2, 5.4),
    "distribution_dpi": 160,
    "parameter_heatmap_figsize": (12.0, 6.0),
    "parameter_line_figsize": (12.0, 6.0),
    "error_bar_figsize": (11.0, 5.5),
    "auto_heatmap_figsize": (7.0, 5.6),
    "auto_plot_dpi": 180,
    "surface_dpi": 220,
    "mesh_dpi": 260,
    "surface_cmap": "jet",
    "mesh_cmap": "jet",
    "surface_elev": 23.0,
    "surface_azim": -125.0,
    "surface_antialiased": True,
    "surface_linewidth": 0.0,
    # 论文风格图的画布尺寸；单位英寸，可直接修改。
    "paper_fig8_figsize": (11.0, 6.5),
    "paper_fig9_figsize": (9.2, 4.8),
    "paper_fig10_figsize": (10.5, 5.3),
    "surface_panel_size": (4.2, 3.4),
    "mesh_panel_size": (2.65, 2.55),
}


# ==================== 8. 断裂与材料拟合参数 ====================
FRACTURE_CONFIG = {
    "y0": 0.495,
    "fixed_k_sp": None,
    "fixed_eta_sp": None,
    "minimum_experiment_samples": 10,
    "curve_points": 501,
    "curve_drop_ratio": 0.10,
    "curve_sustain_points": 3,
}


# ==================== 9. 常用路径 ====================
# 网站默认使用独立的研究数据区，避免把原始输入和生成结果写入源码目录。
# 目录/文件名保留中文语义，并以“1”作为首个工作区编号；网页可一键切换编号。
_data_root = Path(r"D:\research\DATA\Corrosion modelling")
_workspace_id = 1


def _workspace_paths(root: Path, workspace_id: int) -> dict[str, Path]:
    suffix = str(int(workspace_id))
    return {
        "inputs": root / f"任务输入目录{suffix}",
        "outputs": root / f"任务结果目录{suffix}",
        "auto_plots": root / f"自动图片目录{suffix}",
        "morphology_outputs": root / f"形貌参数结果目录{suffix}",
        "curve_outputs": root / f"曲线结果目录{suffix}",
        "fracture_test_data": root / f"断裂试验输入文件{suffix}.csv",
        "material_test_data": root / f"材料试验输入文件{suffix}.csv",
        "long_term_corrosion_data": root / f"长期腐蚀输入文件{suffix}.csv",
        "curve_metadata": root / f"曲线元信息文件{suffix}.csv",
        "curves_dir": root / f"曲线输入目录{suffix}",
    }


PATH_CONFIG = _workspace_paths(_data_root, _workspace_id)


def geometry_values() -> tuple[int, int, int, float]:
    """返回 CA 入口需要的 w、l、n、space。"""
    return (
        int(GEOMETRY_CONFIG["grid_w"]),
        int(GEOMETRY_CONFIG["grid_l"]),
        int(GEOMETRY_CONFIG["grid_n"]),
        float(GEOMETRY_CONFIG["space_z_um"]),
    )


def stage_data_copy() -> np.ndarray:
    """返回目标数据副本，防止入口脚本意外修改全局配置。"""
    return np.array(ACTIVE_STAGE_TARGET_DATA, dtype=float, copy=True)


def manual_stage_data_copy() -> np.ndarray:
    """返回并校验手动目标，供高速版手动模式使用。"""
    data = stage_data_copy()
    if data.ndim != 2 or data.shape[1] != 6:
        raise ValueError(
            "ACTIVE_STAGE_TARGET_DATA 必须是 n×6 数组，列顺序为原高速版六项原始统计量。"
        )
    if data.shape[0] < 1 or not np.isfinite(data).all():
        raise ValueError("ACTIVE_STAGE_TARGET_DATA 必须至少包含一行且全部为有限数值。")
    return data


def print_summary() -> None:
    """打印当前统一配置，便于运行前检查。"""
    w, l, n, space_z = geometry_values()
    xy = float(GEOMETRY_CONFIG["space_xy_um"])
    print("=== 统一参数配置 ===")
    print(f"网格: {w} x {l} x {n} 层")
    print(f"元胞尺寸: X/Y={xy:g} μm, Z={space_z:g} μm")
    print(f"模型物理尺寸: {w * xy / 1000:g} x {l * xy / 1000:g} x {n * space_z / 1000:g} mm")
    print(f"多阶段目标数据: {ACTIVE_STAGE_TARGET_DATA.tolist()}")
    print(f"GA: {STAGE_GA_CONFIG}")
    print(f"Taichi: {TAICHI_CONFIG}")
    print(f"平滑: {POSTPROCESS_CONFIG}")


if __name__ == "__main__":
    print_summary()

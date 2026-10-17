"""统一配置的完整目录及保守资源估算；不改科学公式。"""
from __future__ import annotations

import ast
import math
from pathlib import Path

from .config import default_simulation_config, source_config, validate_simulation_config

GROUP_LABELS = {
    "GEOMETRY_CONFIG": "几何与元胞尺寸", "STAGE_GA_CONFIG": "多阶段遗传算法",
    "SINGLE_STAGE_GA_CONFIG": "单阶段遗传算法", "GA_CONFIG": "遗传算法控制",
    "CA_CONFIG": "元胞腐蚀规则", "TAICHI_CONFIG": "计算后端",
    "POSTPROCESS_CONFIG": "形貌后处理", "MATLAB_CA_COMPARISON_CONFIG": "MATLAB 指标对齐",
    "FIGURE_CONFIG": "绘图外观", "FRACTURE_CONFIG": "断裂与材料拟合",
    "PATH_CONFIG": "任务路径", "ROOT": "任务根目录", "MULTI_CASE_CONFIG": "多工况任务编排",
    "TARGET_SOURCE": "目标来源", "ACTIVE_STAGE_TARGET_DATA": "多阶段六指标目标",
    "SINGLE_STAGE_TARGET_DATA": "单阶段六指标目标",
    "GA_PARAMETER_LOWER_BOUNDS": "GA 参数下界", "GA_PARAMETER_UPPER_BOUNDS": "GA 参数上界",
    "mode": "运行模式",
}
LABELS = {
    "grid_w": "X 向元胞数", "grid_l": "Y 向元胞数", "grid_n": "Z 向元胞层数",
    "space_xy_um": "面内元胞尺寸 / μm", "space_z_um": "厚度方向元胞尺寸 / μm",
    "plate_thickness_um": "原始钢板厚度 / μm", "nind": "种群数量", "F": "CA 步数",
    "selected_count": "每代保留个体数", "maxgen": "最大代数", "parallel_workers": "内部并行进程数",
    "seed": "随机种子", "bits_per_param": "每个参数的二进制位数", "base_px": "初始交叉概率",
    "base_pm": "初始变异概率", "decay_rate": "概率衰减率", "sigma_share": "适应度共享尺度",
    "use_taichi": "启用 Taichi", "arch": "Taichi 架构", "allow_taichi_parallel": "允许 Taichi 与并行共用",
    "verbose": "详细进度输出", "alpha_passive": "钝化系数", "initial_d": "初始扩散参数",
    "initial_cl": "初始氯离子浓度", "initial_enhancement_steps": "初始局部增强步数",
    "initial_enhancement_beta": "初始局部增强系数", "convex_height_limit": "凸起高度上限",
    "gaussian_sigma": "高斯平滑强度", "min_prominence": "极值突出程度",
    "min_distance": "坑中心最小网格距离", "neighborhood": "极值邻域尺寸",
    "watershed_threshold": "分水岭阈值", "enabled": "启用多工况", "run_mode": "工况运行方式",
    "parallel_case_workers": "同时运行工况数", "cases": "工况清单", "sequential_enabled": "启用顺序工况",
    "parallel_enabled": "启用并行工况", "surface_cmap": "曲面配色", "mesh_cmap": "网格配色",
    "fixed_k_sp": "固定应力参数 k", "fixed_eta_sp": "固定应力三轴度参数 η",
    "interactive_window_size": "交互曲面平滑窗口", "auto_plot_window_size": "自动曲面平滑窗口",
    "conv2_window_size": "二维均值卷积窗口", "expand_factor": "矩阵放大倍数",
    "log_normalization": "坑深对数归一化因子", "ca_min_prominence": "CA 极值突出程度",
    "ca_min_distance": "CA 极值最小间距", "dynamic_neighborhood": "按极差选择邻域",
    "threshold_by_jicha": "按极差选择分水岭阈值", "sjb_divisor": "深径比除数",
    "depth_log_scale": "坑深对数换算方式", "depth_log_normalization": "坑深对数归一化",
    "hist_bin_width": "分布直方图柱宽", "interactive_figsize": "交互画布尺寸 / 英寸",
    "interactive_dpi": "交互图分辨率 / DPI", "distribution_figsize": "分布画布尺寸 / 英寸",
    "distribution_dpi": "分布图分辨率 / DPI", "parameter_heatmap_figsize": "参数热图画布 / 英寸",
    "parameter_line_figsize": "参数折线画布 / 英寸", "error_bar_figsize": "误差图画布 / 英寸",
    "auto_heatmap_figsize": "自动热图画布 / 英寸", "auto_plot_dpi": "自动出图分辨率 / DPI",
    "surface_dpi": "曲面图分辨率 / DPI", "mesh_dpi": "网格图分辨率 / DPI",
    "surface_elev": "曲面观察仰角 / 度", "surface_azim": "曲面观察方位 / 度",
    "surface_antialiased": "曲面抗锯齿", "surface_linewidth": "曲面网格线宽",
    "paper_fig8_figsize": "论文图8画布 / 英寸", "paper_fig9_figsize": "论文图9画布 / 英寸",
    "paper_fig10_figsize": "论文图10画布 / 英寸", "surface_panel_size": "曲面子图尺寸 / 英寸",
    "mesh_panel_size": "网格子图尺寸 / 英寸", "y0": "材料拟合基准参数 y0",
    "minimum_experiment_samples": "最少试验样本数", "curve_points": "曲线插值点数",
    "curve_drop_ratio": "曲线下降识别比例", "curve_sustain_points": "连续下降识别点数",
    "inputs": "任务输入目录", "outputs": "任务结果目录", "auto_plots": "自动图片目录",
    "morphology_outputs": "形貌参数结果目录", "curve_outputs": "曲线结果目录",
    "fracture_test_data": "断裂试验输入文件", "material_test_data": "材料试验输入文件",
    "long_term_corrosion_data": "长期腐蚀输入文件", "curve_metadata": "曲线元信息文件",
    "curves_dir": "曲线输入目录",
}
HELP = {
    "GA_PARAMETER_LOWER_BOUNDS": "10个GA参数的下界，按[p_uniform_base,p_passive_base,p_break,cl_threshold,alpha_corrosion,sensitive_point,alpha_p_break,p_h,p_v,p_o]顺序；每项必须小于对应上界，编码和原CA参数含义保持不变。",
    "GA_PARAMETER_UPPER_BOUNDS": "10个GA参数的上界，与下界按同一顺序一一对应；扩大区间会改变搜索空间，需要重新验证拟合结果。",
    "TARGET_SOURCE": "matlab表示从上传MAT中选定六指标变量，manual表示手工输入六指标。网站任务以实际上传选择或手工表格冻结目标，不读取引擎中的本地源路径。",
    "GA_CONFIG.seed": "随机种子控制初始种群、交叉、变异与个体随机种子。严格模式在同一引擎和环境下支持随机数状态恢复；更改种子会创建不同寻优轨迹。",
}


def _usage_scope(group, key, default):
    if group == "POSTPROCESS_CONFIG":
        return ("CA适应度与阶段实际指标" if key in {"gaussian_sigma", "auto_plot_window_size"}
                else "独立形貌分析/出图预留，本任务未使用")
    if group == "FIGURE_CONFIG":
        return ("阶段热图配色" if key == "surface_cmap"
                else "独立科研出图预留，本任务未使用")
    if group == "MATLAB_CA_COMPARISON_CONFIG":
        return ("CA适应度与阶段实际指标" if key in {"min_prominence", "min_distance", "sjb_divisor", "threshold_by_jicha"}
                else "独立分布分析预留，本任务未使用")
    if group == "GEOMETRY_CONFIG" and key == "plate_thickness_um":
        return "后续材料拟合，本任务未使用"
    return default


def value_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def _source_comments():
    """直接读取统一配置行内注释，不复制易失真的参数说明。"""
    text = Path(source_config.__file__).read_text(encoding="utf-8")
    lines = text.splitlines()
    comments = {}
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if not names:
            continue
        for key, value in zip(node.value.keys, node.value.values):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                line = lines[value.end_lineno - 1]
                if "#" in line:
                    comments[f"{names[0]}.{key.value}"] = line.split("#", 1)[1].strip()
    return comments


def simulation_catalog() -> list[dict]:
    defaults, comments = default_simulation_config(), _source_comments()
    entries = []
    managed = {"ROOT", "PATH_CONFIG"}
    deferred = {"FRACTURE_CONFIG"}
    for group, values in defaults.items():
        fields = values.items() if isinstance(values, dict) else [(group, values)]
        for key, value in fields:
            path = f"{group}.{key}" if isinstance(values, dict) else group
            scope = ("任务管理" if group in managed else
                     "多工况调度" if group == "MULTI_CASE_CONFIG" else
                     "目标输入" if group == "TARGET_SOURCE" else
                     "后续材料拟合，本模拟不使用" if group in deferred else "模拟与分析")
            scope = _usage_scope(group, key, scope)
            label = LABELS.get(key, GROUP_LABELS.get(key, key.replace("_", " ")))
            help_text = HELP.get(path, comments.get(path, f"{GROUP_LABELS.get(group, group)}参数 {key}；值沿用统一配置。"))
            if "本任务未使用" in scope:
                help_text += " 可编辑保存供独立分析复用；当前网站CA/GA任务不读取该字段。"
            if group == "ROOT":
                help_text += " 这是网站源码根目录，由服务启动位置管理，不建议修改。"
            elif group == "PATH_CONFIG":
                help_text += " 可在网页中直接编辑；建议使用“数据工作区”快捷区统一生成并应用编号路径。"
            if group in deferred:
                help_text += " 当前 CA/GA 运行链路不消费此字段。"
            entries.append({"path": path, "group": group, "key": key, "label": label,
                            "help": help_text, "type": value_type(value), "value": value,
                            "scope": scope, "editable": group != "ROOT"})
    return entries


def estimate_resources(config: dict, stages: int = 1, run_mode: str = "staged") -> dict:
    validate_simulation_config(config)
    if isinstance(stages, bool) or not isinstance(stages, int) or stages < 1:
        raise ValueError("stages 必须为正整数")
    if run_mode not in {"single", "staged"}:
        raise ValueError("run_mode 必须为 single 或 staged")
    geometry = config["GEOMETRY_CONFIG"]
    settings = config["SINGLE_STAGE_GA_CONFIG" if run_mode == "single" else "STAGE_GA_CONFIG"]
    cells = math.prod(int(geometry[key]) for key in ("grid_w", "grid_l", "grid_n"))
    configured_workers = int(settings["parallel_workers"])
    use_taichi = config["mode"] == "fast" and config["TAICHI_CONFIG"]["use_taichi"]
    workers = (1 if config["mode"] == "strict" or
               (use_taichi and not config["TAICHI_CONFIG"]["allow_taichi_parallel"])
               else configured_workers)
    # NumPy保留a/d两个三维float64数组及二维cl；Taichi路径为整代保留各个体状态。
    state_bytes = (2 * cells + int(geometry["grid_w"]) * int(geometry["grid_l"])) * 8
    retained = state_bytes * int(settings["nind"]) if use_taichi else 0
    # 下一代evaluate_population返回前，GA局部fitness_result仍引用上一代整个人口。
    retained_during_evaluation = retained * (2 if int(settings["maxgen"]) > 2 else 1)
    working = cells * 80 * workers
    overhead = 256 * 1024**2
    transition = 2 * state_bytes if stages > 1 else state_bytes
    phases = {
        "population_evaluation": working + retained_during_evaluation + transition + overhead,
        "checkpoint_or_export": 5 * state_bytes + overhead,
        "plotting": 2 * state_bytes + overhead,
    }
    memory = max(phases.values())
    evaluations = int(settings["nind"]) * (int(settings["maxgen"]) - 1) * stages
    recommendations = ["此为运行前各阶段内存粗估，不是保证上界；临时数组、IPC复制、JIT/GPU和Python/绘图开销随环境变化。",
                       "先用小网格和少代数测量耗时，再扩大计算；无法仅凭配置可靠预测总时长。"]
    recommendations.append("评估次数按原range(1,maxgen)最大代数估算；提前停止会减少次数，最优状态重算可能增加计算。")
    if use_taichi:
        recommendations.append("Taichi高速路径保留整个种群的a/d/cl状态；这部分内存随种群数增长，即使单进程也存在。")
        if int(settings["maxgen"]) > 2:
            recommendations.append("原GA下一代评估返回前仍引用上一代状态，估算阶段峰值包含两代种群同时驻留。")
    if memory > 4 * 1024**3:
        recommendations.append("估算内存超过4 GiB；建议降低并行数或网格层数。")
    if config["mode"] == "strict":
        recommendations.append("严格模式采用固定种子和单进程 NumPy。")
    elif config["mode"] == "pycharm":
        recommendations.append(f"PyCharm模式使用 NumPy ProcessPool，当前配置为 {configured_workers} 个进程；内存不足时优先降低 parallel_workers。")
    return {"estimated": True, "guaranteed_upper_bound": False,
            "run_mode": run_mode, "cells": cells, "workers": workers,
            "configured_workers": configured_workers, "stages": stages,
            "memory_bytes": memory, "memory_gib": round(memory / 1024**3, 3),
            "state_bytes": state_bytes, "working_memory_bytes": working,
            "retained_population_bytes": retained, "phase_peak_bytes": phases,
            "retained_during_evaluation_bytes": retained_during_evaluation,
            "estimated_evaluations": evaluations,
            "estimated_cell_updates": cells * int(settings["F"]) * evaluations,
            "time_seconds": None, "recommendations": recommendations}

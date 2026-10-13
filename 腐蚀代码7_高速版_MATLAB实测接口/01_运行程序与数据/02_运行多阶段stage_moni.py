"""第二步：多阶段 stage_moni 串联入口。

功能目标：
- 严格对应 MATLAB `stage_moni.m`
- 上一阶段的最优 `a/d/cl` 作为下一阶段输入
- 阶段之间仍按顺序串联，阶段内部种群适应度评估对应 MATLAB `parfor`

MATLAB / Python 语法差异提示：
- MATLAB 的 `for i=1:N` 对应 Python `for i in range(N)`
- MATLAB 的矩阵拼接常用 `[]`，Python 常用 `np.zeros` 预分配后再赋值
"""

from __future__ import annotations

import time
from pathlib import Path

from runtime_bootstrap import ensure_taichi_runtime

ensure_taichi_runtime()

import numpy as np

from corrosion_model.stage_moni import StageConfig, run_stage_moni
from unified_config import (
    GA_CONFIG,
    GEOMETRY_CONFIG,
    STAGE_GA_CONFIG,
    TAICHI_CONFIG,
    geometry_values,
    stage_data_copy,
)


def format_elapsed_time(seconds: float) -> str:
    """把秒数格式化成 `时:分:秒`，方便看完整代码耗时。"""
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d} ({seconds:.2f} s)"


def main() -> None:
    start_time = time.perf_counter()  # Time 函数：记录脚本开始时间，用于计算总耗时。
    # 第二步：这里是最常改的参数区。
    # data 的每一行对应一个阶段，列顺序必须和 MATLAB 脚本一致。
    parallel_workers = int(STAGE_GA_CONFIG["parallel_workers"])
    show_ca_iterations = False  # True 时显示更细的 CA 迭代进度；False 时保持并行更快。
    data = stage_data_copy()
    w, l, n, space = geometry_values()
    config = StageConfig(
        w=w,
        l=l,
        n=n,
        space=space,
        F=int(STAGE_GA_CONFIG["F"]),
        nind=int(STAGE_GA_CONFIG["nind"]),
        selected_count=int(STAGE_GA_CONFIG["selected_count"]),
        maxgen=int(STAGE_GA_CONFIG["maxgen"]),
        seed=int(GA_CONFIG["seed"]),
        use_taichi=bool(TAICHI_CONFIG["use_taichi"]),
        parallel_workers=parallel_workers,  # Python Processes 池，对应 MATLAB parfor。
    )

    print("=== 第二步开始：多阶段 stage_moni / Processes 版 ===")
    print(f"阶段数: {data.shape[0]}")
    print(f"Taichi: {config.use_taichi}")
    print(f"Processes 并行池 workers: {parallel_workers}")
    print(
        "Stage/GA 设置: "
        f"w={config.w}, l={config.l}, n={config.n}, F={config.F}, "
        f"nind={config.nind}, selected_count={config.selected_count}, maxgen={config.maxgen}"
    )
    print(
        "进度说明: 后续会显示阶段编号、GA 代数、种群个体评估。"
        + (" CA 迭代将逐步显示。" if show_ca_iterations else " CA 迭代在并行模式下只显示个体级进度。")
    )

    result = run_stage_moni(
        data_x_values=data[:, 0],
        data=data,
        config=config,
        verbose=True if not show_ca_iterations else True,
        progress_label="第二步/Stage",
    )

    out_path = Path(__file__).resolve().with_name("step2_stage_moni_result.npz")
    print(f"[第二步/保存] 正在保存结果到: {out_path}")
    np.savez_compressed(
        out_path,
        perfect_result_sd=result.perfect_result_sd,
        perfect_parameter_sd=result.perfect_parameter_sd,
        stage_numbers=result.stage_numbers,
        a_sd=np.array(result.a_sd, dtype=object),
        d_sd=np.array(result.d_sd, dtype=object),
        cl_sd=np.array(result.cl_sd, dtype=object),
        perfect_a=result.a_sd[-1] if result.a_sd else np.array([]),
        perfect_d=result.d_sd[-1] if result.d_sd else np.array([]),
        perfect_cl=result.cl_sd[-1] if result.cl_sd else np.array([]),
        seed=int(GA_CONFIG["seed"]),
        target_data=data,
        space_xy_um=float(GEOMETRY_CONFIG["space_xy_um"]),
        space_z_um=float(GEOMETRY_CONFIG["space_z_um"]),
    )

    print("=== 第二步完成：多阶段 stage_moni ===")
    print(f"Processes 并行池 workers: {parallel_workers}")
    print(f"结果文件: {out_path}")
    print("perfect_result_sd =")
    print(result.perfect_result_sd)
    print("perfect_parameter_sd =")
    print(result.perfect_parameter_sd)
    elapsed = time.perf_counter() - start_time
    print(f"第二步总耗时: {format_elapsed_time(elapsed)}")


if __name__ == "__main__":
    main()

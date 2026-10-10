"""第一步：单阶段 GA 反演入口。

功能目标：
- 严格对应 MATLAB `GA.m`
- 对应 MATLAB `fitness.m` 中的 `parfor i = 1:NIND`
- 使用 Python `ProcessPoolExecutor` 作为 Processes 并行池

MATLAB / Python 语法差异提示：
- MATLAB 数组从 1 开始，Python 数组从 0 开始
- MATLAB 的列向量在 Python 中常写成 1D `np.ndarray`
- Python 的切片右端不包含，MATLAB 的区间通常两端都包含
"""

from __future__ import annotations

import time
from pathlib import Path

from runtime_bootstrap import ensure_taichi_runtime

ensure_taichi_runtime()

import numpy as np

from corrosion_model.ga import GAConfig, run_ga
from unified_config import (
    GA_CONFIG,
    GEOMETRY_CONFIG,
    SINGLE_STAGE_GA_CONFIG,
    SINGLE_STAGE_TARGET_DATA,
    geometry_values,
)


def format_elapsed_time(seconds: float) -> str:
    """把秒数格式化成 `时:分:秒`，方便看完整代码耗时。"""
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d} ({seconds:.2f} s)"


def main() -> None:
    start_time = time.perf_counter()  # Time 函数：记录脚本开始时间，用于计算总耗时。
    # 第一步：这里是最常改的参数区。
    # 这些参数对应 MATLAB `GA.m` / `fitness.m` / `CA.m` 中的输入。
    use_taichi = False  # 第一步保持 NumPy/Processes 严格对应模式。
    parallel_workers = int(SINGLE_STAGE_GA_CONFIG["parallel_workers"])
    data = SINGLE_STAGE_TARGET_DATA.copy()
    w, l, n, space = geometry_values()
    config = GAConfig(
        nind=int(SINGLE_STAGE_GA_CONFIG["nind"]),
        selected_count=int(SINGLE_STAGE_GA_CONFIG["selected_count"]),
        maxgen=int(SINGLE_STAGE_GA_CONFIG["maxgen"]),
        bits_per_param=int(GA_CONFIG["bits_per_param"]),
        base_px=float(GA_CONFIG["base_px"]),
        base_pm=float(GA_CONFIG["base_pm"]),
        decay_rate=float(GA_CONFIG["decay_rate"]),
        sigma_share=float(GA_CONFIG["sigma_share"]),
        parallel_workers=parallel_workers,  # Python Processes 池，对应 MATLAB parfor。
    )

    print("=== 第一步开始：单阶段 GA / Processes 版 ===")
    print(f"Taichi: {use_taichi}")
    print(f"Processes 并行池 workers: {parallel_workers}")
    print(f"GA 设置: nind={config.nind}, selected_count={config.selected_count}, maxgen={config.maxgen}")
    print(
        "统一尺寸 CA 设置: "
        f"w={w}, l={l}, n={n}, x/y={GEOMETRY_CONFIG['space_xy_um']:g} μm, z={space:g} μm"
    )
    print("进度说明: 后续会显示 GA 代数、种群个体评估和 CA 腐蚀迭代进度。")

    # 第一步：模型尺寸与 CA 迭代参数。
    # w/l/n/space/F 对应 MATLAB 脚本中的网格与迭代设置。
    result = run_ga(
        w=w,
        l=l,
        n=n,
        data_x=float(data[0]),
        data=data,
        a_input=None,
        F=int(SINGLE_STAGE_GA_CONFIG["F"]),
        stage_number=1,
        space=space,
        d_input=None,
        cl_input=None,
        seed=int(GA_CONFIG["seed"]),
        config=config,
        use_taichi=use_taichi,
        parallel_workers=parallel_workers,
        verbose=True,
        progress_label="第一步/GA",
    )

    out_path = Path(__file__).resolve().with_name("step1_ga_result.npz")
    print(f"[第一步/保存] 正在保存结果到: {out_path}")
    np.savez_compressed(
        out_path,
        perfect_result=result.perfect_result,
        perfect_parameter=result.perfect_parameter,
        perfect_a=result.perfect_a,
        perfect_d=result.perfect_d,
        perfect_cl=result.perfect_cl,
        generations=result.generations,
        seed=int(GA_CONFIG["seed"]),
        target_data=data,
        space_xy_um=float(GEOMETRY_CONFIG["space_xy_um"]),
        space_z_um=float(GEOMETRY_CONFIG["space_z_um"]),
    )

    print("=== 第一步完成：单阶段 GA ===")
    print(f"Processes 并行池 workers: {parallel_workers}")
    print(f"结果文件: {out_path}")
    print(f"代际: {result.generations}")
    print("最优参数:", np.array2string(result.perfect_parameter, precision=4))
    print("最优误差:", np.array2string(result.perfect_result, precision=4))
    elapsed = time.perf_counter() - start_time
    print(f"第一步总耗时: {format_elapsed_time(elapsed)}")


if __name__ == "__main__":
    main()

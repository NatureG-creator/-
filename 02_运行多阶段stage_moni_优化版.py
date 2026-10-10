"""第二步：多阶段 stage_moni 优化版入口。

说明：
- 不修改原始 `02_运行多阶段stage_moni.py`
- 仍使用原项目的 `stage_moni -> GA -> fitness -> CA` 计算链
- 显式启用 Taichi 加速路径
- 默认使用 CPU Taichi，避免 Taichi 与多进程同时抢占 CPU
- 关闭详细进度输出，减少控制台 I/O
- 使用 np.savez 而不是 np.savez_compressed，加快结果保存
- 结果保存到独立文件，不覆盖原结果

注意：
该文件属于“低风险入口优化版”。
它不会修改原有数值算法本身，因此加速幅度主要来自 Taichi、减少日志和减少压缩开销。
"""

from __future__ import annotations

import time
from pathlib import Path

from runtime_bootstrap import ensure_taichi_runtime

# 如果当前解释器没有 Taichi，则切换到项目配置的可用运行时。
ensure_taichi_runtime()

import numpy as np

from corrosion_model.stage_moni import StageConfig, run_stage_moni
from corrosion_model.taichi_accel import (
    init_taichi,
    taichi_available,
    taichi_last_error,
)
from unified_config import (
    GA_CONFIG,
    GEOMETRY_CONFIG,
    STAGE_GA_CONFIG,
    geometry_values,
    stage_data_copy,
)


def format_elapsed_time(seconds: float) -> str:
    """把秒数格式化成 时:分:秒。"""
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d} ({seconds:.2f} s)"


def main() -> None:
    start_time = time.perf_counter()

    # ============================================================
    # 1. 加速设置
    # ============================================================

    # 显式启用 Taichi。
    use_taichi = True

    # 推荐先使用 CPU，稳定且与当前项目兼容性更高。
    # 如果以后确认 NVIDIA GPU + Taichi GPU 后端稳定，可测试改为 "gpu"。
    taichi_arch = "cpu"

    # 当前 Taichi CA 内核自身可以利用 CPU 并行。
    # 默认不同时打开 “多进程 + Taichi”，避免 CPU 线程过度抢占。
    allow_taichi_parallel = False

    # 保留原统一配置中的进程数。
    # 当 allow_taichi_parallel=False 且 use_taichi=True 时，
    # fitness.py 会自动避免同时使用 ProcessPoolExecutor。
    parallel_workers = int(STAGE_GA_CONFIG["parallel_workers"])

    # 关闭大量进度输出，减少控制台 I/O。
    verbose = False

    # ============================================================
    # 2. 初始化 Taichi
    # ============================================================

    if use_taichi:
        taichi_ok = init_taichi(taichi_arch)
        if not taichi_ok or not taichi_available():
            reason = taichi_last_error() or "未知原因"
            raise RuntimeError(
                "Taichi 初始化失败，优化版未继续运行。\n"
                f"后端: {taichi_arch}\n"
                f"原因: {reason}"
            )

    # ============================================================
    # 3. 读取统一配置
    # ============================================================

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
        use_taichi=use_taichi,
        parallel_workers=parallel_workers,
        allow_taichi_parallel=allow_taichi_parallel,
        taichi_arch=taichi_arch,
    )

    # ============================================================
    # 4. 显示运行配置
    # ============================================================

    print("=== 第二步开始：多阶段 stage_moni / 优化版 ===")
    print(f"阶段数: {data.shape[0]}")
    print(f"Taichi: {taichi_available()}")
    print(f"Taichi 后端: {taichi_arch}")
    print(f"Taichi 与 Processes 同时开启: {allow_taichi_parallel}")
    print(f"配置中的 Processes workers: {parallel_workers}")
    print(
        "Stage/GA 设置: "
        f"w={config.w}, l={config.l}, n={config.n}, "
        f"F={config.F}, nind={config.nind}, "
        f"selected_count={config.selected_count}, maxgen={config.maxgen}"
    )

    # ============================================================
    # 5. 执行多阶段计算
    # ============================================================

    result = run_stage_moni(
        data_x_values=data[:, 0],
        data=data,
        config=config,
        verbose=verbose,
        progress_label="第二步/优化版",
    )

    # ============================================================
    # 6. 独立保存结果
    # ============================================================

    # 使用独立文件名，不覆盖原始结果。
    out_path = Path(__file__).resolve().with_name(
        "step2_stage_moni_optimized_result.npz"
    )

    print(f"[第二步/优化版/保存] 正在保存结果到: {out_path}")

    # 保存从 main 开始至结果保存前的累计耗时，单位秒；不含下方 NPZ 写盘时间。
    elapsed_seconds = time.perf_counter() - start_time

    # 使用 savez（不压缩）提升保存速度。
    np.savez(
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
        elapsed_seconds=np.array(elapsed_seconds, dtype=np.float64),
        use_taichi=np.array(use_taichi),
        taichi_arch=np.array(taichi_arch),
        parallel_workers=np.array(parallel_workers),
        allow_taichi_parallel=np.array(allow_taichi_parallel),
        target_data=data,
        space_xy_um=np.array(float(GEOMETRY_CONFIG["space_xy_um"])),
        space_z_um=np.array(float(GEOMETRY_CONFIG["space_z_um"])),
    )

    # ============================================================
    # 7. 运行结果
    # ============================================================

    elapsed = time.perf_counter() - start_time

    print("=== 第二步完成：多阶段 stage_moni / 优化版 ===")
    print(f"结果文件: {out_path}")
    print("perfect_result_sd =")
    print(result.perfect_result_sd)
    print("perfect_parameter_sd =")
    print(result.perfect_parameter_sd)
    print(f"已保存的耗时（保存前）: {elapsed_seconds:.2f} s ({elapsed_seconds / 3600.0:.4f} 小时)")
    print(f"总耗时: {format_elapsed_time(elapsed)}")


if __name__ == "__main__":
    main()

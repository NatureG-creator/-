"""第二步高速入口：调用独立底层优化副本，输出字段与原第二步兼容。

默认 NumPy/SciPy + Processes，参数从 unified_config.py 读取。
Taichi 开关、后端和进度开关在 optimization_config.py 中配置。
阶段必须串联；随机种子、目标计算、早停与 GA 选择规则保持原 Python 语义。
"""

from __future__ import annotations

import time
from pathlib import Path

from runtime_bootstrap import ensure_taichi_runtime
from optimization_config import HIGH_SPEED_CONFIG

# 如果当前解释器没有 Taichi，则切换到项目配置的可用运行时。
if HIGH_SPEED_CONFIG["use_taichi"]:
    ensure_taichi_runtime()

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_MATLAB实测目标接口"))
from matlab_target_adapter import load_matlab_stage_data

from corrosion_model.stage_moni_优化版 import StageConfig, run_stage_moni
from corrosion_model.taichi_accel_优化版 import (
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
    progress_log = Path(__file__).resolve().with_name("ga_progress_every_500_generations.jsonl")
    import os
    os.environ["CORROSION_PROGRESS_LOG"] = str(progress_log)
    if progress_log.exists():
        progress_log.unlink()

    # ============================================================
    # 1. 加速设置
    # ============================================================

    use_taichi = bool(HIGH_SPEED_CONFIG["use_taichi"])

    # 推荐先使用 CPU，稳定且与当前项目兼容性更高。
    # 如果以后确认 NVIDIA GPU + Taichi GPU 后端稳定，可测试改为 "gpu"。
    taichi_arch = str(HIGH_SPEED_CONFIG["taichi_arch"])

    # 当前 Taichi CA 内核自身可以利用 CPU 并行。
    # 默认不同时打开 “多进程 + Taichi”，避免 CPU 线程过度抢占。
    allow_taichi_parallel = bool(HIGH_SPEED_CONFIG["allow_taichi_parallel"])

    # 保留原统一配置中的进程数。
    # 当 allow_taichi_parallel=False 且 use_taichi=True 时，
    # fitness.py 会自动避免同时使用 ProcessPoolExecutor。
    parallel_workers = int(STAGE_GA_CONFIG["parallel_workers"])

    # 底层 should_report 控制进度频率；False 可减少控制台输出。
    verbose = bool(HIGH_SPEED_CONFIG["verbose"])

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

    data, matlab_target_path = load_matlab_stage_data()
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

    print("=== 第二步开始：多阶段 stage_moni / 底层高速版 ===")
    print(f"阶段数: {data.shape[0]}")
    print(f"启用 Taichi: {use_taichi}; 内核就绪: {taichi_available()}")
    print(f"Taichi 后端（开启时有效）: {taichi_arch}")
    print(f"Taichi 与 Processes 同时开启: {allow_taichi_parallel}")
    print(f"配置中的 Processes workers: {parallel_workers}")
    print(f"MATLAB实测目标: {matlab_target_path}")
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
        progress_label="第二步/高速版",
    )

    # ============================================================
    # 6. 独立保存结果
    # ============================================================

    # 使用独立文件名，不覆盖原始结果。
    out_path = Path(__file__).resolve().with_name(
        "step2_stage_moni_highspeed_result.npz"
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

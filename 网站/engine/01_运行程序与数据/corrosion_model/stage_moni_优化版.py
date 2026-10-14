"""Multi-stage GA workflow converted from MATLAB `stage_moni.m`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .ga_优化版 import GAConfig, run_ga
from .progress import ProgressTarget, emit_progress


@dataclass
class StageConfig:
    """Configuration for staged corrosion inversion."""

    w: int = 100  # 宽度
    l: int = 100  # 长度
    n: int = 100  # 深度层数
    space: float = 25.0  # 空间步长
    F: int = 2000  # CA 迭代步数
    nind: int = 300  # GA 种群规模
    selected_count: int = 10  # 每代选择个体数
    maxgen: int = 100  # GA 最大代数
    seed: int = 20260624  # 随机种子
    use_taichi: bool = False  # 是否让每个阶段走 Taichi 加速
    parallel_workers: int = 1  # GA 评估时的并行进程数，1 表示串行
    allow_taichi_parallel: bool = False  # True 时允许 Taichi 与 Processes 同时开启
    taichi_arch: str = "cpu"  # Taichi 后端，Processes 同开时建议使用 cpu


@dataclass
class StageResult:
    """Outputs corresponding to `perfect_result_sd`, `perfect_parameter_sd`, and states."""

    perfect_result_sd: np.ndarray
    perfect_parameter_sd: np.ndarray
    a_sd: list[np.ndarray]
    d_sd: list[np.ndarray]
    cl_sd: list[np.ndarray]
    stage_numbers: np.ndarray


def run_stage_moni(
    data_x_values: np.ndarray,
    data: np.ndarray,
    config: StageConfig | None = None,
    a_input: np.ndarray | None = None,
    d_input: np.ndarray | None = None,
    cl_input: np.ndarray | None = None,
    initial_stage_number: int = 1,
    verbose: ProgressTarget = False,
    progress_label: str = "Stage",
) -> StageResult:
    """Run staged GA inversion.

    可调项：`data_x_values`、`data`、`config`、`a_input`、`d_input`、
    `cl_input`、`initial_stage_number`。

    每一阶段结束后，最优 `a/d/CL` 会作为下一阶段初始状态，这正是
    `stage_moni.m` 中 `a_input=d_output/cl_output` 的串联逻辑。
    """
    config = StageConfig() if config is None else config
    data_x_values = np.asarray(data_x_values, dtype=np.float64)
    data = np.asarray(data, dtype=np.float64)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    if data.shape[0] != data_x_values.size:
        raise ValueError("data 行数必须与 data_x_values 长度一致")

    perfect_result_sd = np.zeros((data_x_values.size, 4), dtype=np.float64)
    perfect_parameter_sd = np.zeros((data_x_values.size, 10), dtype=np.float64)
    a_sd: list[np.ndarray] = []
    d_sd: list[np.ndarray] = []
    cl_sd: list[np.ndarray] = []
    stage_numbers = np.zeros(data_x_values.size, dtype=np.int64)

    stage_number = initial_stage_number
    current_a = a_input
    current_d = d_input
    current_cl = cl_input
    ga_config = GAConfig(
        nind=config.nind,
        selected_count=config.selected_count,
        maxgen=config.maxgen,
        parallel_workers=config.parallel_workers,
    )
    emit_progress(verbose, f"[{progress_label}] 开始多阶段寻优：阶段数={data_x_values.size}, Taichi={config.use_taichi}")
    for i, data_x in enumerate(data_x_values):
        emit_progress(verbose, f"[{progress_label}] 进入第 {stage_number} 阶段，目标深度={float(data_x):.4f}")
        result = run_ga(
            config.w,
            config.l,
            config.n,
            float(data_x),
            data[i, :],
            current_a,
            config.F,
            stage_number,
            config.space,
            current_d,
            current_cl,
            seed=config.seed + i,
            config=ga_config,
            use_taichi=config.use_taichi,
            parallel_workers=config.parallel_workers,
            allow_taichi_parallel=config.allow_taichi_parallel,
            taichi_arch=config.taichi_arch,
            verbose=verbose,
            progress_label=f"{progress_label}/Stage{stage_number}",
        )
        perfect_result_sd[i, :] = result.perfect_result
        perfect_parameter_sd[i, :] = result.perfect_parameter
        a_sd.append(result.perfect_a)
        d_sd.append(result.perfect_d)
        cl_sd.append(result.perfect_cl)
        stage_numbers[i] = stage_number
        current_a = result.perfect_a
        current_d = result.perfect_d
        current_cl = result.perfect_cl
        stage_number += 1
    emit_progress(verbose, f"[{progress_label}] 多阶段寻优完成")
    return StageResult(perfect_result_sd, perfect_parameter_sd, a_sd, d_sd, cl_sd, stage_numbers)


def save_stage_result(result: StageResult, path: str | Path) -> None:
    """Save staged scalar outputs to `.npz`.

    Large state arrays are intentionally not saved by default to avoid surprise
    multi-GB files. Save `a_sd/d_sd/cl_sd` separately when needed.
    """
    np.savez_compressed(
        path,
        perfect_result_sd=result.perfect_result_sd,
        perfect_parameter_sd=result.perfect_parameter_sd,
        stage_numbers=result.stage_numbers,
    )

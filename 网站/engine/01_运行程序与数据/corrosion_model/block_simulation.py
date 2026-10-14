"""Block simulation converted from `CS.SINAGAL/CA_single4.m`."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .ca import run_ca
from .progress import ProgressTarget, emit_progress


@dataclass
class BlockSimulationResult:
    """Merged result of the block simulation workflow."""

    a: np.ndarray
    d: np.ndarray
    cl_concentration: np.ndarray
    cs: np.ndarray


def split_uniform_blocks(w: int, l: int, num_blocks: int = 5) -> np.ndarray:
    """Python version of `split_uniform_10_blocks`, returning 1-based coords.

    可调项：`w`、`l`、`num_blocks`。
    """
    edges = np.linspace(1, w + 1, num_blocks + 1)
    coords = np.zeros((num_blocks, 4), dtype=np.int64)
    for i in range(num_blocks):
        x1 = int(np.round(edges[i]))
        x2 = int(np.round(edges[i + 1])) - 1
        coords[i, :] = [x1, x2, 1, l]
    return coords


def run_block_simulation(
    xy: np.ndarray,
    data: np.ndarray,
    data_x: float,
    F: int,
    w: int,
    l: int,
    n: int,
    space: float,
    stage_number: int = 1,
    num_blocks: int = 5,
    seed: int = 20260624,
    use_taichi: bool = False,
    verbose: ProgressTarget = False,
    progress_label: str = "Block",
) -> BlockSimulationResult:
    """Run the block version of the CA simulation.

    可调项：`xy`、`data`、`data_x`、`F`、`w`、`l`、`n`、`space`、
    `stage_number`、`num_blocks`、`seed`、`use_taichi`。

    分块会切断块之间的即时扩散邻接关系，因此它是 `CA_single4.m` 的复刻，
    不是完整区域 `CA.m` 的数值等价替代。
    """
    coords = split_uniform_blocks(w, l, num_blocks)
    full_a = np.zeros((w, l, n + 1), dtype=np.float64)
    full_d = np.zeros((w, l, n + 1), dtype=np.float64)
    full_cl = np.zeros((w, l), dtype=np.float64)
    last_cs = np.zeros(np.asarray(data).size, dtype=np.float64)
    master = np.random.default_rng(seed)
    emit_progress(verbose, f"[{progress_label}] 开始分块模拟：块数={num_blocks}, Taichi={use_taichi}")
    for x1, x2, y1, y2 in coords:
        wb = x2 - x1 + 1
        lb = y2 - y1 + 1
        child_rng = np.random.default_rng(int(master.integers(0, np.iinfo(np.uint32).max)))
        emit_progress(
            verbose,
            f"[{progress_label}] 处理分块 x={x1}:{x2}, y={y1}:{y2}, 尺寸={wb}x{lb}",
        )
        result = run_ca(
            xy,
            F,
            None,
            data,
            data_x,
            n,
            wb,
            lb,
            space,
            None,
            stage_number,
            None,
            child_rng,
            use_taichi=use_taichi,
            verbose=verbose,
            progress_label=f"{progress_label}/Block{x1}-{x2}",
        )
        full_a[x1 - 1 : x2, y1 - 1 : y2, :] = result.a
        full_d[x1 - 1 : x2, y1 - 1 : y2, :] = result.d
        full_cl[x1 - 1 : x2, y1 - 1 : y2] = result.cl_concentration
        last_cs = result.cs
    emit_progress(verbose, f"[{progress_label}] 分块模拟完成")
    return BlockSimulationResult(full_a, full_d, full_cl, last_cs)

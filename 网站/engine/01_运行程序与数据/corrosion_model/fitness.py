"""Fitness evaluation converted from MATLAB `fitness.m`."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass

import numpy as np

from .ca import run_ca
from .progress import ProgressTarget, emit_progress, should_report


_FITNESS_WORKER_CONTEXT: dict[str, object] = {}


def _fitness_worker_init(
    data: np.ndarray,
    data_x: float,
    F: int,
    n: int,
    w: int,
    l: int,
    space: float,
    stage_number: int,
    a_jisuan: np.ndarray | None,
    d_jisuan: np.ndarray | None,
    cl_concentration_jisuan: np.ndarray | None,
    use_taichi: bool = False,
    taichi_arch: str = "cpu",
) -> None:
    """Store shared read-only inputs inside a worker process."""
    if use_taichi:
        from .taichi_accel import init_taichi

        init_taichi(taichi_arch)
    _FITNESS_WORKER_CONTEXT.clear()
    _FITNESS_WORKER_CONTEXT.update(
        data=np.asarray(data, dtype=np.float64),
        data_x=float(data_x),
        F=int(F),
        n=int(n),
        w=int(w),
        l=int(l),
        space=float(space),
        stage_number=int(stage_number),
        a_jisuan=None if a_jisuan is None else np.asarray(a_jisuan, dtype=np.float64),
        d_jisuan=None if d_jisuan is None else np.asarray(d_jisuan, dtype=np.float64),
        cl_concentration_jisuan=None
        if cl_concentration_jisuan is None
        else np.asarray(cl_concentration_jisuan, dtype=np.float64),
    )


def _fitness_worker(task: tuple[int, np.ndarray, int, bool]) -> tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Evaluate one individual inside a worker process."""
    idx, xy_row, seed, use_taichi = task
    ctx = _FITNESS_WORKER_CONTEXT
    result = run_ca(
        np.asarray(xy_row, dtype=np.float64),
        int(ctx["F"]),
        ctx["a_jisuan"],
        np.asarray(ctx["data"], dtype=np.float64),
        float(ctx["data_x"]),
        int(ctx["n"]),
        int(ctx["w"]),
        int(ctx["l"]),
        float(ctx["space"]),
        ctx["d_jisuan"],
        int(ctx["stage_number"]),
        ctx["cl_concentration_jisuan"],
        np.random.default_rng(seed),
        use_taichi=use_taichi,
        verbose=False,
        progress_label=f"Fitness/CA{idx + 1}",
    )
    return (
        idx,
        np.round(np.abs(result.cs), 2),
        result.a,
        result.d,
        result.cl_concentration,
    )


@dataclass
class FitnessResult:
    """Container equivalent to MATLAB `[sd_OBJV, sd_a, sd_d, sd_cl]`."""

    objv: np.ndarray
    a_states: list[np.ndarray]
    d_states: list[np.ndarray]
    cl_states: list[np.ndarray]


def evaluate_population(
    xy: np.ndarray,
    data: np.ndarray,
    data_x: float,
    F: int,
    n: int,
    w: int,
    l: int,
    space: float,
    stage_number: int,
    a_jisuan: np.ndarray | None = None,
    d_jisuan: np.ndarray | None = None,
    cl_concentration_jisuan: np.ndarray | None = None,
    seed: int | None = None,
    use_taichi: bool = False,
    parallel_workers: int = 0,
    allow_taichi_parallel: bool = False,
    taichi_arch: str = "cpu",
    verbose: ProgressTarget = False,
    progress_label: str = "Fitness",
) -> FitnessResult:
    """Python version of `fitness.m`.

    可调项：`xy`、`data`、`data_x`、`F`、`n`、`w`、`l`、`space`、
    `stage_number`、`a_jisuan`、`d_jisuan`、`cl_concentration_jisuan`、`seed`、
    `use_taichi`、`parallel_workers`、`allow_taichi_parallel`。

    MATLAB used `parfor`, but this conversion runs serially by default so the
    random-number call order is deterministic and easier to compare.
    """
    xy = np.asarray(xy, dtype=np.float64)
    data = np.asarray(data, dtype=np.float64)
    nind = xy.shape[0]
    objv = np.zeros((nind, data.size), dtype=np.float64)
    master = np.random.default_rng(seed)
    child_seeds = [int(master.integers(0, np.iinfo(np.uint32).max)) for _ in range(nind)]
    worker_count = int(parallel_workers)
    use_parallel = worker_count > 1 and (allow_taichi_parallel or not use_taichi) and nind > 1
    a_states: list[np.ndarray] = [np.empty(0)] * nind
    d_states: list[np.ndarray] = [np.empty(0)] * nind
    cl_states: list[np.ndarray] = [np.empty(0)] * nind
    emit_progress(verbose, f"[{progress_label}] 开始评估种群：个体数={nind}, Taichi={use_taichi}")
    if use_parallel:
        emit_progress(
            verbose,
            f"[{progress_label}] 启用并行评估：workers={worker_count}, Taichi={use_taichi}",
        )
        tasks = [(i, xy[i, :].copy(), child_seeds[i], use_taichi) for i in range(nind)]
        completed = 0
        with ProcessPoolExecutor(
            max_workers=worker_count,
            initializer=_fitness_worker_init,
            initargs=(
                data,
                data_x,
                F,
                n,
                w,
                l,
                space,
                stage_number,
                a_jisuan,
                d_jisuan,
                cl_concentration_jisuan,
                use_taichi,
                taichi_arch,
            ),
        ) as executor:
            futures = [executor.submit(_fitness_worker, task) for task in tasks]
            for future in as_completed(futures):
                idx, obj_row, a_state, d_state, cl_state = future.result()
                objv[idx, :] = obj_row
                a_states[idx] = a_state
                d_states[idx] = d_state
                cl_states[idx] = cl_state
                completed += 1
                if should_report(completed, nind):
                    emit_progress(
                        verbose,
                        f"[{progress_label}] 已完成 {completed}/{nind} 个体，当前首个目标值={obj_row[0]:.4f}",
                    )
    else:
        for i in range(nind):
            # MATLAB `parfor i=1:NIND` has independent workers; Python uses a
            # reproducible per-individual sub-seed to avoid hidden global state.
            child_seed = child_seeds[i]
            result = run_ca(
                xy[i, :],
                F,
                a_jisuan,
                data,
                data_x,
                n,
                w,
                l,
                space,
                d_jisuan,
                stage_number,
                cl_concentration_jisuan,
                np.random.default_rng(child_seed),
                use_taichi=use_taichi,
                verbose=verbose,
                progress_label=f"{progress_label} 个体 {i + 1}/{nind}",
            )
            objv[i, :] = np.round(np.abs(result.cs), 2)
            a_states[i] = result.a
            d_states[i] = result.d
            cl_states[i] = result.cl_concentration
            if should_report(i + 1, nind):
                emit_progress(
                    verbose,
                    f"[{progress_label}] 已完成 {i + 1}/{nind} 个体，当前首个目标值={objv[i, 0]:.4f}",
                )
    emit_progress(verbose, f"[{progress_label}] 种群评估完成")
    return FitnessResult(objv, a_states, d_states, cl_states)

"""Genetic algorithm operators converted from the MATLAB GA scripts."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import json
import os
from datetime import datetime
from pathlib import Path
from scipy.spatial.distance import cdist
from scipy.stats import qmc

from .matlab_compat import matlab_round
from .fitness_优化版 import FitnessResult, evaluate_population, recover_individual_state
from .progress import ProgressTarget, emit_progress
from unified_config import GA_PARAMETER_LOWER_BOUNDS, GA_PARAMETER_UPPER_BOUNDS

CHECKPOINT_BATCH_SIZE = 5


@dataclass
class GAConfig:
    """Parameters corresponding to the constants at the top of `GA.m`."""

    nind: int = 300  # 种群规模
    lind: int = 10  # 参数个数
    bits_per_param: int = 11  # 每个参数的二进制位数
    selected_count: int = 10  # 每代被选择的个体数
    maxgen: int = 100  # 最大迭代代数
    base_px: float = 0.5  # 初始交叉概率
    base_pm: float = 0.5  # 初始变异概率
    decay_rate: float = 0.2  # 自适应变化速率
    sigma_share: float = 0.3  # 小生境共享阈值
    parallel_workers: int = 1  # 评估种群时的并行进程数，1 表示串行


def latin_begin(
    nind: int,
    lind: int,
    bits_per_param: int,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Python version of `latin_begin.m`.

    可调项：`nind`、`lind`、`bits_per_param`、`rng`。

    MATLAB: `lhsdesign(NIND, LIND)` returns values in [0, 1].
    Python: `scipy.stats.qmc.LatinHypercube` is used for the same design idea,
    but the random stream is not bit-identical to MATLAB.
    """
    rng = np.random.default_rng() if rng is None else rng
    sampler = qmc.LatinHypercube(d=lind, seed=rng)
    population = sampler.random(nind)
    scaled_samples = matlab_round(population * (2**bits_per_param - 1))
    # MATLAB bitget 按参数分块、高位在前；C 顺序 reshape 保持原染色体列排列。
    shifts = np.arange(bits_per_param - 1, -1, -1)
    bits = (scaled_samples.astype(np.int64)[:, :, None] >> shifts) & 1
    return bits.reshape(nind, lind * bits_per_param).astype(np.int8)


def decode_binary_population(
    chrom: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    bits_per_param: int,
) -> np.ndarray:
    """Python version of `er2shi.m`: binary chromosome -> real parameters.

    可调项：`lb`、`ub`、`bits_per_param`。
    """
    chrom = np.asarray(chrom, dtype=np.float64)
    lb = np.asarray(lb, dtype=np.float64)
    ub = np.asarray(ub, dtype=np.float64)
    nind = chrom.shape[0]
    lind = lb.size
    weights = 2.0 ** np.arange(bits_per_param - 1, -1, -1)
    # 对应原 MATLAB 连续 bits 列切片，保留原乘法/除法/加法的顺序。
    int_values = chrom.reshape(nind, lind, bits_per_param) @ weights
    return lb + (ub - lb) * int_values / (2**bits_per_param - 1)


def crossover_population(
    selected: np.ndarray,
    px: float,
    lind: int,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Python version of `jiaocha.m` single-point crossover.

    可调项：`px`、`lind`、`rng`。
    """
    rng = np.random.default_rng() if rng is None else rng
    selected = np.asarray(selected, dtype=np.int8)
    nind, chrom_len = selected.shape
    bits_per_param = chrom_len // lind
    shuffled_indices = rng.permutation(nind)
    shuffled = selected[shuffled_indices, :].copy()
    for i in range(0, nind - 1, 2):
        if rng.random() < px:
            # MATLAB `randi(LIND)` gives 1..LIND; Python gives 0..LIND-1.
            param_idx = rng.integers(0, lind)
            bit_in_param = rng.integers(0, bits_per_param)
            crossover_point = param_idx * bits_per_param + bit_in_param
            temp = shuffled[i, crossover_point:].copy()
            shuffled[i, crossover_point:] = shuffled[i + 1, crossover_point:]
            shuffled[i + 1, crossover_point:] = temp
    return shuffled[shuffled_indices, :]


def mutate_population(
    selected: np.ndarray,
    pm: float,
    rng: np.random.Generator | None = None,
    mutation_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Python version of `mut.m`: flip bits where `rand(size)<pm`.

    可调项：`pm`、`mutation_mask`、`rng`。
    """
    rng = np.random.default_rng() if rng is None else rng
    selected = np.asarray(selected, dtype=np.int8)
    if mutation_mask is None:
        mutation_mask = rng.random(selected.shape) < pm
    out = selected.copy()
    out[mutation_mask] = 1 - out[mutation_mask]
    return out


def tournament_selection(
    fitness: np.ndarray,
    n_selection: int,
    tournament_size: int,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Python version of `tournament_selection.m`.

    可调项：`n_selection`、`tournament_size`、`rng`。

    Returned indices are Python 0-based, while the MATLAB function returns
    1-based indices. All callers in Python must use these directly.
    """
    rng = np.random.default_rng() if rng is None else rng
    fitness = np.asarray(fitness, dtype=np.float64).reshape(-1)
    nind = fitness.size
    selected = np.full(n_selection, -1, dtype=np.int64)
    for i in range(n_selection):
        candidates = rng.choice(nind, size=tournament_size, replace=False)
        while np.any(np.isin(candidates, selected[selected >= 0])):
            candidates = rng.choice(nind, size=tournament_size, replace=False)
        best_local = np.argmax(fitness[candidates])
        selected[i] = candidates[best_local]
    return selected


def shared_fitness(xy: np.ndarray, objv: np.ndarray, sigma_share: float) -> np.ndarray:
    """Apply the niche sharing calculation used in `GA.m`.

    可调项：`sigma_share`。
    """
    fitness = 1.0 / (np.asarray(objv, dtype=np.float64).reshape(-1) + np.finfo(float).eps)
    dist_matrix = cdist(xy, xy)
    np.fill_diagonal(dist_matrix, 0.0)
    share_terms = np.maximum(1.0 - dist_matrix / sigma_share, 0.0)
    sum_shared = np.sum(share_terms, axis=1) + 1.0
    return fitness / sum_shared


@dataclass
class GAResult:
    """Return object matching MATLAB `GA.m` outputs."""

    perfect_result: np.ndarray
    perfect_parameter: np.ndarray
    perfect_a: np.ndarray
    perfect_d: np.ndarray
    perfect_cl: np.ndarray
    generations: int


def combine_objectives(objv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Apply the objective-column edits and weights from `GA.m`."""
    edited = np.array(objv, copy=True, dtype=np.float64)
    if edited.shape[1] >= 6:
        edited = np.delete(edited, 4, axis=1)
        edited[:, 3] = 0.6 * edited[:, 3] + 0.4 * edited[:, 4]
        edited = np.delete(edited, 4, axis=1)
    weights = np.array([0.1, 0.3, 0.2, 0.4], dtype=np.float64)
    weighted = edited[:, :4] @ weights
    return edited[:, :4], weighted


def run_ga(
    w: int,
    l: int,
    n: int,
    data_x: float,
    data: np.ndarray,
    a_input: np.ndarray | None,
    F: int,
    stage_number: int,
    space: float,
    d_input: np.ndarray | None,
    cl_input: np.ndarray | None,
    seed: int = 20260624,
    config: GAConfig | None = None,
    lb: np.ndarray | None = None,
    ub: np.ndarray | None = None,
    use_taichi: bool = False,
    parallel_workers: int | None = None,
    allow_taichi_parallel: bool = False,
    taichi_arch: str = "cpu",
    verbose: ProgressTarget = False,
    progress_label: str = "GA",
    checkpoint=None,
) -> GAResult:
    """Python version of MATLAB `GA.m`.

    可调项：`w`、`l`、`n`、`data_x`、`data`、`F`、`stage_number`、`space`、
    `seed`、`config`、`lb`、`ub`、`use_taichi`、`parallel_workers`。

    This is intentionally serial for reproducibility. Parallel execution would
    change random-number consumption compared with the MATLAB `parfor` run.
    """
    config = GAConfig() if config is None else config
    if parallel_workers is None:
        parallel_workers = config.parallel_workers
    lb = (
        np.asarray(GA_PARAMETER_LOWER_BOUNDS, dtype=np.float64).copy()
        if lb is None
        else np.asarray(lb, dtype=np.float64)
    )
    ub = (
        np.asarray(GA_PARAMETER_UPPER_BOUNDS, dtype=np.float64).copy()
        if ub is None
        else np.asarray(ub, dtype=np.float64)
    )
    data_arr = np.asarray(data, dtype=np.float64)
    if checkpoint is not None and use_taichi:
        raise ValueError("阶段内检查点仅支持 NumPy 模式")
    rng = np.random.default_rng(seed)
    state = checkpoint.load() if checkpoint is not None else None
    if state is not None and state.get("backend") != "pycharm":
        raise ValueError("检查点计算模式不匹配")
    if state is None:
        chrom = latin_begin(config.nind, config.lind, config.bits_per_param, rng)
        state = dict(backend="pycharm", generation=1, chrom=chrom.tolist(),
                     rng_state=rng.bit_generator.state, evaluation_seed=None, scores={},
                     next_individual=0, best_state=None, best_result=None,
                     best_parameter=None, last_generation=0, completed=False)
        if checkpoint is not None: checkpoint.save(state)
    else:
        chrom = np.asarray(state["chrom"], dtype=np.int8)
        rng.bit_generator.state = state["rng_state"]
    perfect_result: np.ndarray | None = None
    perfect_parameter: np.ndarray | None = None
    perfect_a: np.ndarray | None = None
    perfect_d: np.ndarray | None = None
    perfect_cl: np.ndarray | None = None
    last_gen = 1
    if state["best_state"] is not None:
        saved = checkpoint.load_arrays(state["best_state"])
        perfect_result = np.asarray(state["best_result"], dtype=float)
        perfect_parameter = np.asarray(state["best_parameter"], dtype=float)
        perfect_a, perfect_d, perfect_cl = saved["a"], saved["d"], saved["cl"]
        last_gen = int(state["last_generation"])
    def numeric_list(values):
        return [float(x) if np.isfinite(x) else str(float(x)) for x in values]
    pending_checkpoint_individuals = 0
    def save_individual(index, row):
        nonlocal pending_checkpoint_individuals
        state["scores"][str(index)] = numeric_list(row)
        state["next_individual"] = len(state["scores"])
        pending_checkpoint_individuals += 1
        if pending_checkpoint_individuals >= CHECKPOINT_BATCH_SIZE:
            checkpoint.save(state)
            pending_checkpoint_individuals = 0
    emit_progress(verbose, f"[{progress_label}] 开始寻优：最大代数={config.maxgen}, 种群={config.nind}, Taichi={use_taichi}")
    for gen in range(int(state["generation"]), config.maxgen) if not state["completed"] else ():
        last_gen = gen
        xy = decode_binary_population(chrom, lb, ub, config.bits_per_param)
        current_px = max(0.6, min(0.95, config.base_px * np.exp(-config.decay_rate * (gen / config.maxgen))))
        current_pm = max(0.01, min(0.3, config.base_pm + (0.3 - config.base_pm) * (gen / config.maxgen)))
        if stage_number == 1:
            a_jisuan = None
            d_jisuan = None
            cl_jisuan = None
        else:
            a_jisuan = a_input
            d_jisuan = d_input
            cl_jisuan = cl_input
        if state["evaluation_seed"] is None:
            state["evaluation_seed"] = int(rng.integers(0, np.iinfo(np.uint32).max))
            state["rng_state"] = rng.bit_generator.state
            if checkpoint is not None: checkpoint.save(state)
        fitness_result: FitnessResult = evaluate_population(
            xy,
            data_arr,
            data_x,
            F,
            n,
            w,
            l,
            space,
            stage_number,
            a_jisuan,
            d_jisuan,
            cl_jisuan,
            seed=state["evaluation_seed"],
            use_taichi=use_taichi,
            parallel_workers=parallel_workers,
            allow_taichi_parallel=allow_taichi_parallel,
            taichi_arch=taichi_arch,
            verbose=verbose,
            progress_label=f"{progress_label}/Gen{gen}",
            retain_states=use_taichi,
            saved_scores=state["scores"] if checkpoint is not None else None,
            on_individual=save_individual if checkpoint is not None else None,
        )
        edited_objv, weighted_objv = combine_objectives(fitness_result.objv)
        fitness = shared_fitness(xy, weighted_objv, config.sigma_share)
        i_min = int(np.argmin(weighted_objv))
        if perfect_result is None or np.sum(perfect_result) > np.sum(edited_objv[i_min, :]):
            perfect_result = edited_objv[i_min, :].copy()
            perfect_parameter = xy[i_min, :].copy()
            if fitness_result.a_states[i_min].size:
                perfect_a = fitness_result.a_states[i_min]
                perfect_d = fitness_result.d_states[i_min]
                perfect_cl = fitness_result.cl_states[i_min]
            else:
                # 仅当全局最优记录更新时恢复状态，避免每代额外计算未改善的个体。
                best = recover_individual_state(
                    i_min, fitness_result, xy, data_arr, data_x, F, n, w, l, space,
                    stage_number, a_jisuan, d_jisuan, cl_jisuan,
                    use_taichi=use_taichi, verbose=verbose,
                    progress_label=f"{progress_label}/Gen{gen}/最优状态恢复",
                )
                perfect_a, perfect_d, perfect_cl = best.a, best.d, best.cl_concentration
        def save_generation(completed):
            nonlocal pending_checkpoint_individuals
            if checkpoint is None: return
            # Large arrays change only when the global best improves.
            if state["best_result"] != numeric_list(perfect_result) or state["best_state"] is None:
                state["best_state"] = checkpoint.save_arrays(a=perfect_a, d=perfect_d, cl=perfect_cl)
            state.update(best_result=numeric_list(perfect_result),
                         best_parameter=perfect_parameter.tolist(), last_generation=gen,
                         generation=gen+1, chrom=chrom.tolist(), rng_state=rng.bit_generator.state,
                         evaluation_seed=None, scores={}, next_individual=0, completed=completed)
            checkpoint.save(state)
            pending_checkpoint_individuals = 0
        if np.sum(perfect_result) <= 0.01:
            save_generation(True)
            break
        sorted_indices = np.argsort(fitness)
        diversity = float(np.std(fitness))
        tournament_size = max(2, int(matlab_round(5 * diversity)))
        tournament_size = min(tournament_size, config.nind)
        selected_indices = tournament_selection(
            fitness, config.selected_count, tournament_size, rng
        )
        selected = chrom[selected_indices, :]
        crossed = crossover_population(selected, current_px, config.lind, rng)
        mutated = mutate_population(crossed, current_pm, rng)
        worst = sorted_indices[: mutated.shape[0]]
        chrom[worst, :] = mutated
        save_generation(gen == config.maxgen-1)
        if checkpoint is None:
            state.update(evaluation_seed=None, scores={})
        emit_progress(
            verbose,
            f"[{progress_label}] 已完成第 {gen} 代，当前最优误差={np.array2string(perfect_result, precision=4)}",
        )
        # 每500代写一条记录；只增加日志，不改变CA/GA计算和随机数顺序。
        if gen % 500 == 0 or gen == config.maxgen - 1:
            log_path = os.environ.get("CORROSION_PROGRESS_LOG")
            if log_path:
                record = dict(time=datetime.now().isoformat(timespec="seconds"),
                              stage=stage_number, generation=gen,
                              best_error=np.asarray(perfect_result, dtype=float).tolist())
                log_file = Path(log_path)
                log_file.parent.mkdir(parents=True, exist_ok=True)
                with log_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
    if perfect_result is None:
        raise RuntimeError("GA did not evaluate any generation")
    emit_progress(verbose, f"[{progress_label}] 寻优完成，共迭代 {last_gen} 代")
    return GAResult(
        perfect_result,
        perfect_parameter,
        perfect_a,
        perfect_d,
        perfect_cl,
        last_gen,
    )

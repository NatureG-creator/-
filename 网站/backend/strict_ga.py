"""Resumable single-worker GA using the copied scientific operators."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import numpy as np

from .checkpoint import CheckpointStore
from .config import source_config
from corrosion_model.ca_优化版 import run_ca
from corrosion_model.ga_优化版 import (
    GAConfig, GAResult, combine_objectives, crossover_population,
    decode_binary_population, latin_begin, mutate_population, shared_fitness,
    tournament_selection,
)
from corrosion_model.matlab_compat import matlab_round


def _save_best(folder: Path, a: np.ndarray, d: np.ndarray, cl: np.ndarray) -> None:
    path = folder / "best.npz"
    temporary = folder / "best.tmp"
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, a=a, d=d, cl=cl)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _apply_scientific_settings(config: dict) -> None:
    for name in ("GEOMETRY_CONFIG", "GA_CONFIG", "CA_CONFIG", "POSTPROCESS_CONFIG", "MATLAB_CA_COMPARISON_CONFIG"):
        current = getattr(source_config, name)
        current.clear()
        current.update(config[name])


def run_strict_stage(
    target: np.ndarray,
    config: dict,
    stage_number: int,
    folder: Path,
    fingerprint: str,
    *,
    a_input: np.ndarray | None = None,
    d_input: np.ndarray | None = None,
    cl_input: np.ndarray | None = None,
    progress: Callable[[dict], None] | None = None,
) -> GAResult:
    _apply_scientific_settings(config)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = CheckpointStore(folder, fingerprint)
    settings = config["STAGE_GA_CONFIG"]
    ga_options = config["GA_CONFIG"]
    geometry = config["GEOMETRY_CONFIG"]
    ga_config = GAConfig(
        nind=int(settings["nind"]), selected_count=int(settings["selected_count"]),
        maxgen=int(settings["maxgen"]), parallel_workers=1,
        bits_per_param=int(ga_options["bits_per_param"]),
        base_px=float(ga_options["base_px"]), base_pm=float(ga_options["base_pm"]),
        decay_rate=float(ga_options["decay_rate"]), sigma_share=float(ga_options["sigma_share"]),
    )
    w, l, n = (int(geometry[key]) for key in ("grid_w", "grid_l", "grid_n"))
    space = float(geometry["space_z_um"])
    F = int(settings["F"])
    data = np.asarray(target, dtype=np.float64)
    data_x = float(data[0])
    lb = np.asarray(config["GA_PARAMETER_LOWER_BOUNDS"], dtype=np.float64)
    ub = np.asarray(config["GA_PARAMETER_UPPER_BOUNDS"], dtype=np.float64)
    state = checkpoint.load()
    rng = np.random.default_rng(int(ga_options["seed"]) + stage_number - 1)
    if state is None:
        chrom = latin_begin(ga_config.nind, ga_config.lind, ga_config.bits_per_param, rng)
        state = {
            "generation": 1, "next_individual": 0, "chrom": chrom.tolist(),
            "rng_state": rng.bit_generator.state, "evaluation_seed": None,
            "child_seeds": None, "objv": None, "best_result": None,
            "best_parameter": None, "best_generation": None,
        }
        checkpoint.save(state)
    else:
        rng.bit_generator.state = state["rng_state"]

    best_result = None if state["best_result"] is None else np.asarray(state["best_result"], dtype=np.float64)
    best_parameter = None if state["best_parameter"] is None else np.asarray(state["best_parameter"], dtype=np.float64)
    final_generation = int(state["generation"])
    for gen in range(int(state["generation"]), ga_config.maxgen):
        final_generation = gen
        chrom = np.asarray(state["chrom"], dtype=np.int8)
        xy = decode_binary_population(chrom, lb, ub, ga_config.bits_per_param)
        if state["child_seeds"] is None:
            evaluation_seed = int(rng.integers(0, np.iinfo(np.uint32).max))
            master = np.random.default_rng(evaluation_seed)
            child_seeds = [int(master.integers(0, np.iinfo(np.uint32).max)) for _ in range(ga_config.nind)]
            objv = np.zeros((ga_config.nind, data.size), dtype=np.float64)
            state.update(evaluation_seed=evaluation_seed, child_seeds=child_seeds,
                         objv=objv.tolist(), rng_state=rng.bit_generator.state)
            checkpoint.save(state)
        else:
            child_seeds = state["child_seeds"]
            objv = np.asarray(state["objv"], dtype=np.float64)
        for index in range(int(state["next_individual"]), ga_config.nind):
            result = run_ca(
                xy[index], F, a_input if stage_number > 1 else None,
                data, data_x, n, w, l, space,
                d_input if stage_number > 1 else None, stage_number,
                cl_input if stage_number > 1 else None,
                np.random.default_rng(child_seeds[index]), use_taichi=False,
                verbose=False,
            )
            objv[index, :] = np.round(np.abs(result.cs), 2)
            state["next_individual"] = index + 1
            state["objv"] = objv.tolist()
            checkpoint.save(state)
            if progress is not None:
                progress({"stage": stage_number, "generation": gen,
                          "completed_individuals": index + 1,
                          "total_individuals": ga_config.nind})

        edited_objv, weighted_objv = combine_objectives(objv)
        fitness = shared_fitness(xy, weighted_objv, ga_config.sigma_share)
        best_index = int(np.argmin(weighted_objv))
        if best_result is None or np.sum(best_result) > np.sum(edited_objv[best_index, :]):
            best_result = edited_objv[best_index, :].copy()
            best_parameter = xy[best_index, :].copy()
            best = run_ca(
                xy[best_index], F, a_input if stage_number > 1 else None,
                data, data_x, n, w, l, space,
                d_input if stage_number > 1 else None, stage_number,
                cl_input if stage_number > 1 else None,
                np.random.default_rng(child_seeds[best_index]), use_taichi=False,
                verbose=False,
            )
            if not np.array_equal(np.round(np.abs(best.cs), 2), objv[best_index], equal_nan=True):
                raise RuntimeError("最优个体重放结果不一致，已停止以保护结果")
            _save_best(folder, best.a, best.d, best.cl_concentration)
            state["best_result"] = best_result.tolist()
            state["best_parameter"] = best_parameter.tolist()
            state["best_generation"] = gen
            checkpoint.save(state)
        if np.sum(best_result) <= 0.01:
            break
        current_px = max(0.6, min(0.95, ga_config.base_px * np.exp(-ga_config.decay_rate * (gen / ga_config.maxgen))))
        current_pm = max(0.01, min(0.3, ga_config.base_pm + (0.3 - ga_config.base_pm) * (gen / ga_config.maxgen)))
        sorted_indices = np.argsort(fitness)
        diversity = float(np.std(fitness))
        tournament_size = min(max(2, int(matlab_round(5 * diversity))), ga_config.nind)
        selected_indices = tournament_selection(fitness, ga_config.selected_count, tournament_size, rng)
        selected = chrom[selected_indices, :]
        crossed = crossover_population(selected, current_px, ga_config.lind, rng)
        mutated = mutate_population(crossed, current_pm, rng)
        chrom[sorted_indices[:mutated.shape[0]], :] = mutated
        state.update(generation=gen + 1, next_individual=0, chrom=chrom.tolist(),
                     rng_state=rng.bit_generator.state, evaluation_seed=None,
                     child_seeds=None, objv=None)
        checkpoint.save(state)
    if best_result is None or best_parameter is None:
        raise RuntimeError("没有完成任何 GA 个体")
    with np.load(folder / "best.npz", allow_pickle=False) as best_arrays:
        return GAResult(best_result, best_parameter, best_arrays["a"].copy(),
                        best_arrays["d"].copy(), best_arrays["cl"].copy(), final_generation)

"""Resumable single-worker GA using the copied scientific operators."""

from __future__ import annotations

import copy
import csv
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

import numpy as np

from .checkpoint import CheckpointStore, _replace_bytes
from .config import source_config
from corrosion_model.ca_优化版 import run_ca
from corrosion_model.ga_优化版 import (
    GAConfig, GAResult, combine_objectives, crossover_population,
    decode_binary_population, latin_begin, mutate_population, shared_fitness,
    tournament_selection,
)
from corrosion_model.matlab_compat import matlab_round


def _apply_scientific_settings(config: dict) -> None:
    for name in ("GEOMETRY_CONFIG", "GA_CONFIG", "CA_CONFIG", "POSTPROCESS_CONFIG", "MATLAB_CA_COMPARISON_CONFIG"):
        current = getattr(source_config, name)
        current.clear()
        current.update(config[name])


@contextmanager
def scientific_settings(config: dict):
    """Imported engine dictionaries are task-scoped and restored on every exit."""
    names = ("GEOMETRY_CONFIG", "GA_CONFIG", "CA_CONFIG", "POSTPROCESS_CONFIG",
             "MATLAB_CA_COMPARISON_CONFIG")
    saved = {name: copy.deepcopy(getattr(source_config, name)) for name in names}
    _apply_scientific_settings(config)
    try:
        yield
    finally:
        _apply_scientific_settings(saved)


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
    run_mode: str = "staged",
    timing: dict | None = None,
    engine_fingerprint: str | None = None,
) -> GAResult:
    with scientific_settings(config):
        return _run_strict_stage(target, config, stage_number, folder, fingerprint,
                                 a_input=a_input, d_input=d_input, cl_input=cl_input,
                                 progress=progress, run_mode=run_mode, timing=timing,
                                 engine_fingerprint=engine_fingerprint)


def _run_strict_stage(target, config, stage_number, folder, fingerprint, *,
                      a_input, d_input, cl_input, progress, run_mode, timing,
                      engine_fingerprint):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = CheckpointStore(folder, fingerprint, engine_fingerprint=engine_fingerprint)
    if run_mode not in {"single", "staged"}:
        raise ValueError("运行方式必须是 single 或 staged")
    settings = config["SINGLE_STAGE_GA_CONFIG" if run_mode == "single" else "STAGE_GA_CONFIG"]
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
    read_started = time.perf_counter()
    state = checkpoint.load()
    read_seconds = time.perf_counter() - read_started
    stage_timing = {key: 0.0 for key in ("reading_seconds", "compute_seconds",
                                       "checkpoint_seconds", "export_seconds")}
    if state is not None:
        stage_timing.update(state.get("timing", {}))
    stage_timing["reading_seconds"] += read_seconds
    checkpoint_count = 0 if state is None else state.get("checkpoint_count", 0)
    checkpoint_bytes = 0 if state is None else state.get("checkpoint_bytes", 0)
    last_checkpoint_seconds = 0.0

    def event(phase, generation, completed, **extra):
        if timing is not None:
            timing.update({f"stage_{stage_number}_{key}": value for key, value in stage_timing.items()})
        if progress is not None:
            progress({"stage": stage_number, "generation": generation,
                      "completed_individuals": completed, "total_individuals": ga_config.nind,
                      "phase": phase, "timing": dict(stage_timing),
                      "checkpoint_count": checkpoint_count, "checkpoint_bytes": checkpoint_bytes,
                      "last_checkpoint_seconds": last_checkpoint_seconds,
                      "recovered_from_previous": checkpoint.recovered_from_previous, **extra})

    def save():
        nonlocal checkpoint_count, checkpoint_bytes, last_checkpoint_seconds
        state["timing"] = dict(stage_timing)
        state["checkpoint_count"] = checkpoint_count + 1
        state["checkpoint_bytes"] = checkpoint_bytes
        started = time.perf_counter()
        checkpoint.save(state)
        last_checkpoint_seconds = time.perf_counter() - started
        stage_timing["checkpoint_seconds"] += last_checkpoint_seconds
        checkpoint_count += 1
        checkpoint_bytes += checkpoint.path.stat().st_size

    def export_convergence():
        import io
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(["generation", "error_mean", "error_nonuniform",
                         "error_mu_ratio", "error_depth_combined", "weighted_error", "best_error"])
        for record in state["convergence"]:
            writer.writerow([record["generation"], *record["four_errors"],
                             record["weighted_error"], record["best_error"]])
        started = time.perf_counter()
        _replace_bytes(folder / "convergence.csv", buffer.getvalue().encode("utf-8-sig"))
        stage_timing["export_seconds"] += time.perf_counter() - started

    rng = np.random.default_rng(int(ga_options["seed"]) + stage_number - 1)
    if state is None:
        chrom = latin_begin(ga_config.nind, ga_config.lind, ga_config.bits_per_param, rng)
        state = {
            "generation": 1, "next_individual": 0, "chrom": chrom.tolist(),
            "rng_state": rng.bit_generator.state, "evaluation_seed": None,
            "child_seeds": None, "objv": None, "best_result": None,
            "best_parameter": None, "best_generation": None,
            "best_state": None, "last_generation": 0, "completed": False,
            "convergence": [],
        }
        save()
    else:
        rng.bit_generator.state = state["rng_state"]

    best_result = None if state["best_result"] is None else np.asarray(state["best_result"], dtype=np.float64)
    best_parameter = None if state["best_parameter"] is None else np.asarray(state["best_parameter"], dtype=np.float64)
    final_generation = int(state["last_generation"])
    for gen in range(int(state["generation"]), ga_config.maxgen) if not state["completed"] else ():
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
            save()
        else:
            child_seeds = state["child_seeds"]
            objv = np.asarray(state["objv"], dtype=np.float64)
        for index in range(int(state["next_individual"]), ga_config.nind):
            event("compute", gen, index)
            compute_started = time.perf_counter()
            result = run_ca(
                xy[index], F, a_input if stage_number > 1 else None,
                data, data_x, n, w, l, space,
                d_input if stage_number > 1 else None, stage_number,
                cl_input if stage_number > 1 else None,
                np.random.default_rng(child_seeds[index]), use_taichi=False,
                verbose=False,
            )
            stage_timing["compute_seconds"] += time.perf_counter() - compute_started
            objv[index, :] = np.round(np.abs(result.cs), 2)
            state["next_individual"] = index + 1
            state["objv"] = objv.tolist()
            save()
            del result  # Individual arrays are replayable from the immutable seed.
            event("checkpoint", gen, index + 1)

        compute_started = time.perf_counter()
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
            stage_timing["compute_seconds"] += time.perf_counter() - compute_started
            snapshot_started = time.perf_counter()
            state["best_state"] = checkpoint.save_arrays(
                a=best.a, d=best.d, cl=best.cl_concentration, raw_cs=best.cs)
            stage_timing["checkpoint_seconds"] += time.perf_counter() - snapshot_started
            checkpoint_bytes += (folder / state["best_state"]["file"]).stat().st_size
            state["best_result"] = best_result.tolist()
            state["best_parameter"] = best_parameter.tolist()
            state["best_generation"] = gen
            save()
            del best
        else:
            stage_timing["compute_seconds"] += time.perf_counter() - compute_started
        record = {"generation": gen, "four_errors": best_result.tolist(),
                  "weighted_error": float(best_result @ np.array([.1, .3, .2, .4])),
                  "best_error": float(np.sum(best_result))}
        state["last_generation"] = gen
        if np.sum(best_result) <= 0.01:
            state["convergence"].append(record)
            state["completed"] = True
            save()
            export_convergence()
            event("generation_completed", gen, ga_config.nind,
                  **{key: value for key, value in record.items() if key != "generation"})
            break
        compute_started = time.perf_counter()
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
                     child_seeds=None, objv=None, completed=gen + 1 >= ga_config.maxgen)
        state["convergence"].append(record)
        stage_timing["compute_seconds"] += time.perf_counter() - compute_started
        save()
        export_convergence()
        event("generation_completed", gen, ga_config.nind,
              **{key: value for key, value in record.items() if key != "generation"})
    if best_result is None or best_parameter is None:
        raise RuntimeError("没有完成任何 GA 个体")
    read_started = time.perf_counter()
    best_arrays = checkpoint.load_arrays(state["best_state"])
    stage_timing["reading_seconds"] += time.perf_counter() - read_started
    export_convergence()
    if timing is not None:
        timing.update({f"stage_{stage_number}_{key}": value for key, value in stage_timing.items()})
    return GAResult(best_result, best_parameter, best_arrays["a"],
                    best_arrays["d"], best_arrays["cl"], final_generation)

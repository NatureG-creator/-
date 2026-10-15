"""One backend per fresh process, with explicit initialization and warm samples."""
from __future__ import annotations

import functools
import json
import multiprocessing
import sys
import time
from pathlib import Path

import numpy as np

from .benchmark import MODES, compare_arrays, verify_arch
from .strict_ga import _apply_scientific_settings, scientific_settings
from corrosion_model.fitness_优化版 import _fitness_worker_init as _base_worker_init


class BackendUnavailable(RuntimeError):
    pass


def initialize_backend(arch):
    try:
        import taichi as ti
        from corrosion_model.taichi_accel_优化版 import init_taichi, taichi_last_error
        if not init_taichi(arch):
            raise BackendUnavailable("Taichi初始化不可用：" + str(taichi_last_error()))
        actual = str(ti.lang.impl.current_cfg().arch)
        verify_arch(arch, actual)
        return actual
    except (ImportError, OSError, ValueError) as exc:
        raise BackendUnavailable("Taichi依赖或设备不可用：" + str(exc)) from exc


def configured_initializer(config, *args):
    _apply_scientific_settings(config)
    if args[11]:
        initialize_backend(args[12])
    _base_worker_init(*args)


def run_trial(spec: dict, mode: str, folder: Path) -> dict:
    import corrosion_model.fitness_优化版 as fitness
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    options, config = spec["options"], spec["config"]
    use_taichi = mode.startswith("taichi")
    arch = "gpu" if "gpu" in mode else "cpu"
    workers = min(options["workers"], options["population"]) if mode.endswith("parallel") else 1
    started = time.perf_counter()
    actual = initialize_backend(arch) if use_taichi else "cpu"
    initialization_seconds = time.perf_counter() - started
    kwargs = dict(xy=np.asarray(spec["population"]), data=np.asarray(spec["target"]),
                  data_x=float(spec["target"][0]), F=options["steps"], n=options["grid_n"],
                  w=options["grid_w"], l=options["grid_l"],
                  space=float(config["GEOMETRY_CONFIG"]["space_z_um"]), stage_number=1,
                  seed=options["seed"], use_taichi=use_taichi, parallel_workers=workers,
                  allow_taichi_parallel=True, taichi_arch=arch, retain_states=True)
    previous_initializer = fitness._fitness_worker_init
    previous_executor = fitness.ProcessPoolExecutor
    fitness._fitness_worker_init = functools.partial(configured_initializer, config)
    fitness.ProcessPoolExecutor = functools.partial(previous_executor,
                                                   mp_context=multiprocessing.get_context("spawn"))
    samples, repeat_comparisons = [], []
    first_seconds = None
    child_seeds = []
    try:
        with scientific_settings(config):
            for index in range(options["repeats"] + 1):
                tick = time.perf_counter()
                result = fitness.evaluate_population(**kwargs)
                child_seeds = list(result.child_seeds)
                if use_taichi:
                    import taichi as ti
                    ti.sync()
                seconds = time.perf_counter() - tick
                if index == 0:
                    first_seconds = seconds
                else:
                    samples.append(seconds)
                # Keep a representative measured run, never the untimed export in samples.
                destination = folder / ("first_arrays.npz" if index == 0 else "arrays.npz")
                np.savez(destination, objv=result.objv, a=np.stack(result.a_states),
                         d=np.stack(result.d_states), cl=np.stack(result.cl_states))
                del result
                if index:
                    repeat_comparisons.append(compare_arrays(folder / "first_arrays.npz", destination))
    finally:
        fitness._fitness_worker_init = previous_initializer
        fitness.ProcessPoolExecutor = previous_executor
    return {"mode": mode, "label": MODES[mode], "state": "completed", "actual_arch": actual,
            "workers": workers, "initialization_seconds": initialization_seconds,
            "first_seconds": first_seconds, "samples_seconds": samples,
            "median_seconds": float(np.median(samples)), "min_seconds": min(samples),
            "max_seconds": max(samples), "repeat_exact": all(x["exact"] for x in repeat_comparisons),
            "repeat_comparisons": repeat_comparisons, "child_seeds": child_seeds}


def main():
    spec_path, mode, destination = sys.argv[1:]
    folder = Path(destination)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        result = run_trial(json.loads(Path(spec_path).read_text(encoding="utf-8")), mode, folder)
    except BackendUnavailable as exc:
        result = {"mode": mode, "label": MODES[mode], "state": "unavailable", "reason": str(exc)}
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = {"mode": mode, "label": MODES[mode], "state": "failed", "reason": str(exc)}
    from .runner import _atomic_json
    _atomic_json(folder / "trial.json", result)


if __name__ == "__main__":
    main()

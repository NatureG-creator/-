"""Frozen, bounded performance experiments; no changes to scientific kernels."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

from .config import validate_simulation_config, validate_targets

MODES = {
    "numpy_serial": "NumPy · 单进程",
    "numpy_parallel": "NumPy · 多进程",
    "taichi_cpu": "Taichi CPU · 单进程",
    "taichi_gpu": "Taichi GPU · 单进程",
    "taichi_cpu_parallel": "Taichi CPU · 多进程",
    "taichi_gpu_parallel": "Taichi GPU · 多进程",
}
SCOPE_NOTE = ("固定种群的一代适应度评估：从初始状态开始，使用所选目标行，"
              "不运行前序阶段、GA选择/交叉/变异或多工况。首次评估含惰性编译；"
              "预热后样本包含CA、原形貌后处理及数组传输；重建池口径另含建池，常驻池复用已建worker，"
              "不含Python启动、设备初始化和文件导出。不能外推完整GA速度。")


def _integer(options, name, default, low, high):
    value = options.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value != int(value) or not low <= value <= high:
        raise ValueError(f"{name} 必须为 {low} 到 {high} 的整数")
    return int(value)


def prepare_benchmark(payload: dict) -> dict:
    config = validate_simulation_config(copy.deepcopy(payload["config"]))
    targets = copy.deepcopy(payload.get("targets"))
    validate_targets(targets, "staged")
    supplied = payload.get("options", {})
    if not isinstance(supplied, dict):
        raise ValueError("options 必须是对象")
    options = {name: _integer(supplied, name, default, low, high) for name, default, low, high in (
        ("grid_w", 40, 2, 1000), ("grid_l", 40, 2, 1000), ("grid_n", 16, 2, 1000),
        ("steps", 8, 1, 10000), ("population", 6, 2, 500), ("workers", 2, 2, 16),
        ("repeats", 3, 1, 7), ("seed", config["GA_CONFIG"]["seed"], 0, 4294967295),
        ("timeout_seconds", 300, 10, 1800), ("target_index", 0, 0, len(targets) - 1),
        ("threads_per_worker", 1, 1, 16), ("cpu_budget", min(os.cpu_count() or 1, 256), 1, min(os.cpu_count() or 1, 256)),
        ("generations", 3, 1, 10))}
    modes = supplied.get("modes", list(MODES)[:4])
    if not isinstance(modes, list) or not modes or any(not isinstance(x, str) or x not in MODES for x in modes):
        raise ValueError("请选择有效的性能对比方案")
    options["modes"] = ["numpy_serial"] + [m for m in MODES if m != "numpy_serial" and m in modes]
    for name, default, allowed in (("pool_policies", ["recreate"], {"recreate", "persistent"}),):
        selected = supplied.get(name, default)
        if not isinstance(selected, list) or not selected or any(not isinstance(x, str) or x not in allowed for x in selected):
            raise ValueError(f"{name} 选项无效")
        options[name] = list(dict.fromkeys(selected))
    for name, default, low, high, limit in (("seeds", [options["seed"]], 0, 4294967295, 3),
                                            ("worker_counts", [options["workers"]], 2, 16, 4)):
        selected = supplied.get(name, default)
        if name == "seeds" and selected == []:
            selected = default
        if not isinstance(selected, list) or not 1 <= len(selected) <= limit:
            raise ValueError(f"{name} 必须有1到{limit}个整数")
        options[name] = list(dict.fromkeys(_integer({name: x}, name, low, low, high) for x in selected))
    options["workload"] = supplied.get("workload", "population")
    options["order_mode"] = supplied.get("order_mode", "fixed")
    if options["workload"] not in {"population", "short_ga"} or options["order_mode"] not in {"fixed", "random"}:
        raise ValueError("workload或order_mode选项无效")
    selected_default = min(options["population"] - 1, int(config["STAGE_GA_CONFIG"]["selected_count"]))
    options["selected_count"] = _integer(supplied, "selected_count", selected_default, 1, options["population"] - 1)
    options["retain_detail"] = supplied.get("retain_detail", True)
    if not isinstance(options["retain_detail"], bool):
        raise ValueError("retain_detail 必须是布尔值")
    parallel_requested = any(m.endswith("parallel") for m in options["modes"])
    effective_workers = min(max(options["worker_counts"]), options["population"]) if parallel_requested else 1
    if effective_workers * options["threads_per_worker"] > options["cpu_budget"]:
        raise ValueError("进程数×每进程线程数超过CPU线程预算，请明确调整参数")
    cells = options["grid_w"] * options["grid_l"] * (options["grid_n"] + 1)
    # Conservative host-array estimate, including baseline+current and worker copies.
    state_bytes = options["grid_w"] * options["grid_l"] * (2 * (options["grid_n"] + 1) + 1) * 8
    estimated = state_bytes * (4 * options["population"] + 3 * effective_workers + 4)
    variants = build_variants({"options": options})
    generations = options["generations"] if options["workload"] == "short_ga" else 1
    work = cells * options["steps"] * options["population"] * (options["repeats"] + 1) * len(variants) * generations
    if estimated > 1024 ** 3 or work > 2_000_000_000:
        raise ValueError("测速资源预算超过1 GiB主机数组估算或20亿元胞步；请明确减小网格、步数、种群、重复数或方案数。参数没有自动缩小。")
    config["GEOMETRY_CONFIG"].update({name: options[name] for name in ("grid_w", "grid_l", "grid_n")})
    config["GA_CONFIG"]["seed"] = options["seed"]
    from corrosion_model.ga_优化版 import decode_binary_population, latin_begin
    bits = int(config["GA_CONFIG"]["bits_per_param"])
    populations = {}
    for seed in options["seeds"]:
        chromosomes = latin_begin(options["population"], 10, bits, np.random.default_rng(seed))
        populations[str(seed)] = decode_binary_population(chromosomes,
                             np.asarray(config["GA_PARAMETER_LOWER_BOUNDS"]),
                             np.asarray(config["GA_PARAMETER_UPPER_BOUNDS"]), bits).tolist()
    population = populations[str(options["seeds"][0])]
    frozen = {"config": config, "target": targets[options["target_index"]],
              "options": options, "population": population, "populations": populations}
    if payload.get("initial_state_info"):
        frozen["initial_state_info"] = copy.deepcopy(payload["initial_state_info"])
    frozen["stage_number"] = int(payload.get("stage_number", 1))
    encoded = json.dumps(frozen, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    return {"kind": "benchmark", **frozen, "input_hash": hashlib.sha256(encoded).hexdigest(),
            "estimated_host_array_bytes": estimated, "estimated_work": work,
            "scope_note": SCOPE_NOTE if options["workload"] == "population" else
            "短程原GA：保留原选择/交叉/变异与提前停止规则；计入寻优，不含检查点、绘图和文件导出。代数上限与实际代数分别记录。"}


def build_variants(spec):
    options = spec["options"]
    variants = []
    for seed in options.get("seeds", [options["seed"]]):
        baseline_id = f"numpy_serial__s{seed}"
        for mode in options["modes"]:
            parallel = mode.endswith("parallel")
            for workers in options.get("worker_counts", [options["workers"]]) if parallel else [1]:
                for policy in options.get("pool_policies", ["recreate"]) if parallel else ["direct"]:
                    variant_id = baseline_id if mode == "numpy_serial" else f"{mode}__{policy}__w{workers}__s{seed}"
                    variants.append({"mode": mode, "variant_id": variant_id, "baseline_id": baseline_id,
                                     "workers": min(workers, options["population"]), "requested_workers": workers, "seed": seed,
                                     "pool_policy": policy, "workload": options.get("workload", "population"),
                                     "threads_per_worker": options.get("threads_per_worker", 1)})
    if options.get("order_mode") == "random":
        np.random.default_rng(options["seed"]).shuffle(variants)
    return variants


def verify_arch(requested: str, actual: str) -> None:
    cpu = any(name in actual.lower() for name in ("x64", "arm64", "cpu"))
    if (requested == "gpu" and cpu) or (requested == "cpu" and not cpu):
        raise ValueError(f"请求{requested.upper()}，实际架构为{actual}；禁止把CPU回退记作GPU测速")


def compare_arrays(reference: Path, candidate: Path) -> dict:
    rows = {}
    with np.load(reference, allow_pickle=False) as left, np.load(candidate, allow_pickle=False) as right:
        for key in ("objv", "a", "d", "cl"):
            a, b = left[key], right[key]
            shape_match = a.shape == b.shape
            finite, exact, close = True, shape_match, shape_match
            maximum, squared, count = 0.0, 0.0, 0
            if shape_match:
                flat_a, flat_b = a.ravel(), b.ravel()
                for start in range(0, a.size, 262144):
                    x, y = flat_a[start:start+262144], flat_b[start:start+262144]
                    valid = bool(np.isfinite(x).all() and np.isfinite(y).all())
                    finite = finite and valid
                    mismatches = int(np.count_nonzero(x != y))
                    count += mismatches
                    exact = exact and valid and mismatches == 0
                    close = close and valid and (mismatches == 0 if key == "a" else np.allclose(x, y, rtol=1e-7, atol=1e-9))
                    if valid:
                        delta = x.astype(np.float64) - y.astype(np.float64)
                        maximum = max(maximum, float(np.max(np.abs(delta), initial=0)))
                        squared += float(np.dot(delta, delta))
            rows[key] = {"exact": exact, "within_tolerance": close, "shape_match": shape_match,
                         "max_abs_diff": maximum if shape_match and finite and math.isfinite(maximum) else None,
                         "rmse": math.sqrt(squared/a.size) if shape_match and finite and a.size and math.isfinite(squared) else None,
                         "mismatch_count": count if shape_match else None,
                         "mismatch_fraction": count/a.size if shape_match and a.size else None,
                         "categorical": key == "a"}
    return {"exact": all(x["exact"] for x in rows.values()),
            "within_tolerance": all(x["within_tolerance"] for x in rows.values()),
            "rtol": 1e-7, "atol": 1e-9, "arrays": rows}

"""Frozen, bounded performance experiments; no changes to scientific kernels."""
from __future__ import annotations

import copy
import hashlib
import json
import math
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
              "预热后样本包含进程池创建、CA、原形貌后处理及数组传输，"
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
        ("timeout_seconds", 300, 10, 1800), ("target_index", 0, 0, len(targets) - 1))}
    modes = supplied.get("modes", list(MODES)[:4])
    if not isinstance(modes, list) or not modes or any(not isinstance(x, str) or x not in MODES for x in modes):
        raise ValueError("请选择有效的性能对比方案")
    options["modes"] = ["numpy_serial"] + [m for m in MODES if m != "numpy_serial" and m in modes]
    cells = options["grid_w"] * options["grid_l"] * (options["grid_n"] + 1)
    # Conservative host-array estimate, including baseline+current and worker copies.
    state_bytes = options["grid_w"] * options["grid_l"] * (2 * (options["grid_n"] + 1) + 1) * 8
    estimated = state_bytes * (4 * options["population"] + 3 * options["workers"] + 4)
    work = cells * options["steps"] * options["population"] * (options["repeats"] + 1) * len(options["modes"])
    if estimated > 1024 ** 3 or work > 2_000_000_000:
        raise ValueError("测速资源预算超过1 GiB主机数组估算或20亿元胞步；请明确减小网格、步数、种群、重复数或方案数。参数没有自动缩小。")
    config["GEOMETRY_CONFIG"].update({name: options[name] for name in ("grid_w", "grid_l", "grid_n")})
    config["GA_CONFIG"]["seed"] = options["seed"]
    from corrosion_model.ga_优化版 import decode_binary_population, latin_begin
    rng = np.random.default_rng(options["seed"])
    bits = int(config["GA_CONFIG"]["bits_per_param"])
    chromosomes = latin_begin(options["population"], 10, bits, rng)
    population = decode_binary_population(chromosomes,
                                         np.asarray(config["GA_PARAMETER_LOWER_BOUNDS"]),
                                         np.asarray(config["GA_PARAMETER_UPPER_BOUNDS"]), bits).tolist()
    frozen = {"config": config, "target": targets[options["target_index"]],
              "options": options, "population": population}
    encoded = json.dumps(frozen, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    return {"kind": "benchmark", **frozen, "input_hash": hashlib.sha256(encoded).hexdigest(),
            "estimated_host_array_bytes": estimated, "scope_note": SCOPE_NOTE}


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
            finite = bool(np.isfinite(a).all() and np.isfinite(b).all())
            exact = bool(shape_match and finite and np.array_equal(a, b))
            close = bool(shape_match and finite and np.allclose(a, b, rtol=1e-7, atol=1e-9))
            delta = a.astype(np.float64) - b.astype(np.float64) if shape_match and finite else None
            rows[key] = {"exact": exact, "within_tolerance": close, "shape_match": shape_match,
                         "max_abs_diff": None if delta is None else float(np.max(np.abs(delta))),
                         "rmse": None if delta is None else float(np.sqrt(np.mean(delta * delta)))}
    return {"exact": all(x["exact"] for x in rows.values()),
            "within_tolerance": all(x["within_tolerance"] for x in rows.values()),
            "rtol": 1e-7, "atol": 1e-9, "arrays": rows}

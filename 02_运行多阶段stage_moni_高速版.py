"""第二步高速入口：调用独立底层优化副本，输出字段与原第二步兼容。

默认 NumPy/SciPy + Processes，参数从 unified_config.py 读取。
Taichi 开关、后端和进度开关在 unified_config.py 中配置。
阶段必须串联；随机种子、目标计算、早停与 GA 选择规则保持原 Python 语义。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
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
from target_source import validate_target_source

from corrosion_model.stage_moni_优化版 import StageConfig, run_stage_moni
from corrosion_model.taichi_accel_优化版 import (
    init_taichi,
    taichi_available,
    taichi_last_error,
)
from unified_config import (
    GA_CONFIG,
    GEOMETRY_CONFIG,
    MULTI_CASE_CONFIG,
    STAGE_GA_CONFIG,
    TARGET_SOURCE,
    geometry_values,
    manual_stage_data_copy,
    stage_data_copy,
)


def format_elapsed_time(seconds: float) -> str:
    """把秒数格式化成 时:分:秒。"""
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d} ({seconds:.2f} s)"


def _safe_case_name(name: str) -> str:
    """清理工况名，防止工况名形成非法或越界路径。"""
    value = re.sub(r'[\\/:*?"<>|]', "_", str(name).strip())
    value = value.strip(" .")
    if not value or value in {".", ".."}:
        raise ValueError("工况名不能为空。")
    return value


def _configured_run_mode() -> str:
    """读取统一运行方式；没有新配置时回退到旧的混合模式。"""
    mode = str(MULTI_CASE_CONFIG.get("run_mode", "mixed")).strip().lower()
    if mode not in {"single", "sequential", "parallel", "mixed"}:
        raise ValueError(
            "MULTI_CASE_CONFIG['run_mode'] 必须是 single、sequential、parallel 或 mixed。"
        )
    return mode


def _configured_cases(run_mode: str | None = None) -> list[tuple[Path, str, str]]:
    """读取代码内清单；支持一个字典、多个字典或直接填写文件路径。"""
    if validate_target_source(TARGET_SOURCE) != "matlab":
        raise ValueError("代码内多工况清单要求 TARGET_SOURCE='matlab'。")
    entries = MULTI_CASE_CONFIG.get("cases", [])
    if not isinstance(entries, list) or not entries:
        raise ValueError("MULTI_CASE_CONFIG['cases'] 不能为空。")

    selected_mode = run_mode or _configured_run_mode()
    resolved: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if isinstance(entry, str):
            entry = {"matlab_target": entry}
        if not isinstance(entry, dict):
            raise TypeError(f"第 {index} 个多工况配置必须是字典或文件路径字符串。")

        raw_target = entry.get("matlab_target", entry.get("path", ""))
        target = Path(str(raw_target)).expanduser()
        if not target.is_file():
            raise FileNotFoundError(
                f"第 {index} 个工况的 MATLAB 目标文件不存在：{target}"
            )

        raw_name = str(entry.get("case_name", "")).strip()
        # 不填写工况名时，自动使用目标文件所在文件夹名。
        case_name = _safe_case_name(raw_name or target.parent.name or target.stem)

        entry_mode = str(entry.get("mode", "sequential")).strip().lower()
        if selected_mode == "parallel":
            mode = "parallel"
        elif selected_mode in {"single", "sequential"}:
            mode = "sequential"
        else:
            mode = entry_mode
        if mode not in {"sequential", "parallel"}:
            raise ValueError(
                f"工况 {case_name} 的 mode 必须是 'sequential' 或 'parallel'，实际为：{mode}"
            )
        if case_name in seen:
            raise ValueError(f"多工况名称重复：{case_name}")
        seen.add(case_name)
        resolved.append((target, case_name, mode))
    return resolved


def _run_parallel_case_group(cases: list[tuple[Path, str, str]]) -> None:
    """用独立 Python 子进程运行并行工况，隔离环境变量和进度日志。"""
    if not cases:
        return
    max_parallel = int(
        MULTI_CASE_CONFIG.get("parallel_case_workers", max(1, len(cases)))
    )
    if max_parallel < 1:
        raise ValueError("parallel_case_workers 必须是正整数。")

    script = Path(__file__).resolve()
    for offset in range(0, len(cases), max_parallel):
        batch = cases[offset : offset + max_parallel]
        processes = []
        for target, name, _ in batch:
            command = [
                sys.executable,
                str(script),
                "--matlab-target",
                str(target),
                "--case-name",
                name,
            ]
            processes.append(subprocess.Popen(command))

        failures = []
        for (target, name, _), process in zip(batch, processes):
            return_code = process.wait()
            if return_code != 0:
                failures.append(f"{name} (退出码 {return_code})")
        if failures:
            raise RuntimeError("并行工况失败：" + ", ".join(failures))


def run_case(target_file: str | None = None, case_name: str | None = None) -> Path:
    start_time = time.perf_counter()
    selected_target = Path(target_file).expanduser() if target_file else None
    if selected_target is not None and not selected_target.is_file():
        raise FileNotFoundError(f"指定的 MATLAB 目标文件不存在：{selected_target}")
    source_mode = validate_target_source(TARGET_SOURCE)
    if source_mode == "manual":
        if selected_target is not None:
            raise ValueError("TARGET_SOURCE='manual' 时不能同时指定 --matlab-target。")
        data = manual_stage_data_copy()
        matlab_target_path = Path(__file__).resolve().with_name("unified_config.py")
    else:
        if selected_target is None:
            data, matlab_target_path = load_matlab_stage_data()
        else:
            data, matlab_target_path = load_matlab_stage_data(selected_target)

    # 指定工况名后，进度和结果都写入独立目录；无工况名时保留原默认输出路径。
    resolved_case = _safe_case_name(case_name) if case_name else (
        _safe_case_name(matlab_target_path.parent.name) if selected_target is not None else None
    )
    if resolved_case:
        case_dir = Path(__file__).resolve().with_name("结果文件") / resolved_case
        case_dir.mkdir(parents=True, exist_ok=True)
        progress_log = case_dir / "ga_progress_every_500_generations.jsonl"
    else:
        case_dir = None
        progress_log = Path(__file__).resolve().with_name("ga_progress_every_500_generations.jsonl")
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
    print(f"目标来源: {source_mode}")
    print(f"目标数据文件/配置: {matlab_target_path}")
    print(
        "Stage/GA 设置: "
        f"w={config.w}, l={config.l}, n={config.n}, "
        f"F={config.F}, nind={config.nind}, "
        f"selected_count={config.selected_count}, maxgen={config.maxgen}"
    )
    print(
        "物理元胞尺寸: "
        f"X/Y={float(GEOMETRY_CONFIG['space_xy_um']):g} μm, "
        f"Z={float(GEOMETRY_CONFIG['space_z_um']):g} μm; "
        f"CA域={config.w * float(GEOMETRY_CONFIG['space_xy_um']):g} × "
        f"{config.l * float(GEOMETRY_CONFIG['space_xy_um']):g} × "
        f"{config.n * float(GEOMETRY_CONFIG['space_z_um']):g} μm"
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

    # 指定工况时每组结果进入自己的目录；默认仍使用原高速版结果路径。
    out_path = (
        case_dir / "step2_stage_moni_highspeed_result.npz"
        if case_dir is not None
        else Path(__file__).resolve().with_name("step2_stage_moni_highspeed_result.npz")
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
        target_source=np.array(source_mode),
        matlab_target_path=np.array(str(matlab_target_path)),
        case_name=np.array(resolved_case or "default"),
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
    return out_path


def main(target_file: str | None = None, case_name: str | None = None) -> None:
    """运行命令行单组，或按 unified_config.py 的 run_mode 运行工况清单。"""
    # 命令行参数优先，保持原有单组运行方式不变。
    if target_file is not None or case_name is not None:
        run_case(target_file=target_file, case_name=case_name)
        return

    if bool(MULTI_CASE_CONFIG.get("enabled", False)):
        run_mode = _configured_run_mode()
        cases = _configured_cases(run_mode)
        if run_mode == "single":
            if len(cases) != 1:
                raise ValueError("run_mode='single' 时，cases 中必须只保留一个 MATLAB 文件。")
            target, name, _ = cases[0]
            print(f"=== 单工况模式：{name} ===")
            run_case(target_file=str(target), case_name=name)
            return

        if run_mode == "sequential":
            print(f"=== 多工况顺序模式：共 {len(cases)} 组 ===")
            for index, (target, name, _) in enumerate(cases, start=1):
                print(f"=== 顺序工况 {index}/{len(cases)}：{name} ===")
                run_case(target_file=str(target), case_name=name)
            print("=== 多工况顺序模式全部完成 ===")
            return

        if run_mode == "parallel":
            print(
                "=== 多工况并行模式："
                f"共 {len(cases)} 组，同时运行数={int(MULTI_CASE_CONFIG.get('parallel_case_workers', len(cases)))} ==="
            )
            # 只有一个文件时直接运行，避免额外创建子进程。
            if len(cases) == 1:
                target, name, _ = cases[0]
                run_case(target_file=str(target), case_name=name)
            else:
                _run_parallel_case_group(cases)
            print("=== 多工况并行模式全部完成 ===")
            return

        # mixed 保留旧版：按每个 case 的 mode 分成顺序组和并行组。
        sequential_cases = [case for case in cases if case[2] == "sequential"]
        parallel_cases = [case for case in cases if case[2] == "parallel"]
        sequential_enabled = bool(MULTI_CASE_CONFIG.get("sequential_enabled", True))
        parallel_enabled = bool(MULTI_CASE_CONFIG.get("parallel_enabled", False))
        if sequential_cases and not sequential_enabled:
            raise ValueError("存在 mode='sequential' 的工况，但 sequential_enabled=False。")
        if parallel_cases and not parallel_enabled:
            raise ValueError("存在 mode='parallel' 的工况，但 parallel_enabled=False。")
        if not sequential_cases and not parallel_cases:
            raise ValueError("MULTI_CASE_CONFIG['cases'] 中没有有效工况。")

        print(
            "=== 多工况模式："
            f"顺序 {len(sequential_cases)} 组，并行 {len(parallel_cases)} 组 ==="
        )
        if sequential_cases:
            for index, (target, name, _) in enumerate(sequential_cases, start=1):
                print(f"=== 顺序工况 {index}/{len(sequential_cases)}：{name} ===")
                run_case(target_file=str(target), case_name=name)
        if parallel_cases:
            print(
                "=== 并行工况开始："
                f"同时运行数={int(MULTI_CASE_CONFIG.get('parallel_case_workers', 1))} ==="
            )
            _run_parallel_case_group(parallel_cases)
        print("=== 多工况模式全部完成 ===")
        return

    run_case()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="运行指定 MATLAB 腐蚀工况的高速版 CA-GA")
    parser.add_argument(
        "--matlab-target",
        default=None,
        help="某一工况的 matlab_target.mat；不填写时读取实测目标/latest_original_target.txt",
    )
    parser.add_argument(
        "--case-name",
        default=None,
        help="结果工况名；填写后保存到 结果文件/<工况名>/，不覆盖其他工况",
    )
    args = parser.parse_args()
    main(target_file=args.matlab_target, case_name=args.case_name)

r"""第五步：从 CA 腐蚀结果提取断裂准则所需的形貌与截面参数。

运行示例：
    .\.venv\Scripts\python.exe .\腐蚀综合代码\05_提取腐蚀形貌参数.py

本步骤只读取第一步或第二步的 `.npz` 结果，不会重新运行 CA 或 GA。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from corrosion_model.fracture_parameters import compute_fracture_parameters, write_parameter_exports
from corrosion_model.geometry import PaperGeometry
from unified_config import GEOMETRY_CONFIG, PATH_CONFIG


# 第五步的几何参数统一由 unified_config.py 管理，避免这里再次出现一套尺寸。
SPACE_XY_UM = float(GEOMETRY_CONFIG["space_xy_um"])
SPACE_Z_UM = float(GEOMETRY_CONFIG["space_z_um"])
PLATE_THICKNESS_UM = float(GEOMETRY_CONFIG["plate_thickness_um"])
DEFAULT_OUTPUT_DIR = Path(PATH_CONFIG["morphology_outputs"])


def format_elapsed_time(seconds: float) -> str:
    """Format elapsed seconds as hour:minute:second."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d} ({seconds:.2f} s)"


def discover_stage_result() -> Path:
    """Find the most recently modified second-step result, including Taichi variants."""
    candidates = [
        SCRIPT_DIR / "step2_stage_moni_result.npz",
        SCRIPT_DIR / "step2_stage_moni_taichi_result.npz",
        SCRIPT_DIR / "step2_stage_moni_taichi_parallel_result.npz",
    ]
    available = [path for path in candidates if path.exists()]
    if not available:
        raise FileNotFoundError("未找到第二步 .npz 结果。请先运行第二步，或用 --result 指定结果文件。")
    return max(available, key=lambda path: path.stat().st_mtime)


def load_ca_state(result_path: str | Path) -> np.ndarray:
    """Load the final CA matrix from the fields saved by the existing entry scripts."""
    path = Path(result_path)
    with np.load(path, allow_pickle=True) as data:
        if "perfect_a" in data.files:
            a_output = np.asarray(data["perfect_a"])
        elif "a_sd" in data.files:
            # MATLAB stage series -> Python object array; the last item is the final stage.
            states = np.asarray(data["a_sd"], dtype=object).reshape(-1)
            if states.size == 0:
                raise ValueError("结果文件中的 a_sd 为空，无法提取最终腐蚀状态。")
            a_output = np.asarray(states[-1])
        else:
            raise KeyError("结果文件缺少 perfect_a/a_sd，无法提取腐蚀元胞矩阵。")
    if a_output.ndim != 3:
        raise ValueError(f"最终腐蚀元胞矩阵必须为三维，当前形状为 {a_output.shape}。")
    return a_output


def main(argv: list[str] | None = None) -> int:
    start_time = time.perf_counter()
    parser = argparse.ArgumentParser(description="第五步：提取腐蚀形貌和断裂准则参数")
    parser.add_argument("--result", default="", help="第二步或第一步 .npz 结果文件；留空自动选择最新第二步结果")
    parser.add_argument("--thickness-um", type=float, default=PLATE_THICKNESS_UM, help="真实试件原始板厚 t，单位 μm")
    parser.add_argument("--space-xy-um", type=float, default=SPACE_XY_UM, help="论文元胞 x/y 尺寸，单位 μm")
    parser.add_argument("--space-z-um", type=float, default=SPACE_Z_UM, help="论文元胞 z 尺寸，单位 μm")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="CSV/JSON 输出目录")
    args = parser.parse_args(argv)

    result_path = Path(args.result) if args.result else discover_stage_result()
    print("=== 第五步开始：断裂准则腐蚀形貌参数提取 ===")
    print(f"[第五步/读取] 结果文件: {result_path}")
    print(f"[第五步/参数] 原始板厚 t = {args.thickness_um:.6g} μm")
    print(f"[第五步/参数] 元胞尺寸 = {args.space_xy_um:.6g} x {args.space_xy_um:.6g} x {args.space_z_um:.6g} μm")

    a_output = load_ca_state(result_path)
    print(f"[第五步/读取] a_output 网格 = {a_output.shape[0]} x {a_output.shape[1]} x {a_output.shape[2] - 1}")
    print("[第五步/计算] 正在计算截面损伤与腐蚀坑形貌...")
    geometry = PaperGeometry(args.space_xy_um, args.space_z_um, args.thickness_um)
    metrics, pit_details = compute_fracture_parameters(a_output=a_output, geometry=geometry)
    metrics["source_npz"] = str(result_path)

    print("[第五步/保存] 正在写入 CSV、JSON 和腐蚀坑明细...")
    paths = write_parameter_exports(args.output_dir, metrics, pit_details)
    print(f"[第五步/结果] control_direction = {metrics['control_direction']}")
    print(f"[第五步/结果] Save = {metrics['save_um2']:.8f} μm^2")
    print(f"[第五步/结果] Smin = {metrics['smin_um2']:.8f} μm^2")
    print(f"[第五步/结果] ds = {metrics['ds']:.8f} %  （论文式(4)百分数口径）")
    print(f"[第五步/结果] hmax = {metrics['hmax_um']:.6g} μm")
    print(f"[第五步/结果] D = {metrics['d_at_hmax_um']:.6g} μm")
    print(f"[第五步/结果] 真实试件板厚 t = {metrics['plate_thickness_um']/1000:.6g} mm")
    print(f"[第五步/结果] rho = {metrics['rho_at_hmax']:.8g}")
    print(f"[第五步/结果] lambda = {metrics['lambda']:.8g}")
    print(f"[第五步/结果] lambda_rho = {metrics['lambda_rho']:.8g}")
    print(f"[第五步/保存] 汇总 CSV: {paths['csv']}")
    print(f"[第五步/保存] 汇总 JSON: {paths['json']}")
    print(f"[第五步/保存] 腐蚀坑 CSV: {paths['pits_csv']}")
    print(f"第五步总耗时: {format_elapsed_time(time.perf_counter() - start_time)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

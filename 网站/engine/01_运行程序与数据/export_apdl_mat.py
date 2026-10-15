"""把模拟或实测表面保存为 APDL 可读取的 MATLAB MAT 文件。

输出格式保持与 Fanmian.mat / zhengmian.mat 一致：
  - 反面：MAT 中只保存二维 double 变量 F_filled；
  - 正面：MAT 中只保存二维 double 变量 Z_filled。

本程序不重采样，输入矩阵的行列尺寸原样保留。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy.io import loadmat, savemat


def _as_numeric_2d(value: object, source: Path) -> np.ndarray:
    arr = np.asarray(value)
    if arr.ndim != 2 or not np.issubdtype(arr.dtype, np.number):
        raise ValueError(f"{source} 中的表面变量必须是二维数值矩阵，当前为 {arr.shape}。")
    arr = np.asarray(arr, dtype=np.float64)
    if not np.isfinite(arr).all():
        raise ValueError(f"{source} 中的表面变量包含 NaN 或 Inf。")
    return arr


def load_measured_matrix(path: str | Path, variable: str | None = None) -> tuple[str, np.ndarray]:
    """读取已有二维 MAT，优先识别 Z_filled/F_filled，并保留原始尺寸。"""
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"实测 MAT 文件不存在：{source}")
    data = loadmat(source)
    if variable:
        if variable not in data:
            raise KeyError(f"{source} 中不存在变量 {variable}。")
        return variable, _as_numeric_2d(data[variable], source)
    for name in ("Z_filled", "F_filled"):
        if name in data:
            return name, _as_numeric_2d(data[name], source)
    raise KeyError(f"{source} 未找到 Z_filled 或 F_filled 二维变量。")


def _load_npz_array(data: np.lib.npyio.NpzFile, preferred: str, series: str) -> np.ndarray:
    if preferred in data.files:
        arr = np.asarray(data[preferred])
        if arr.ndim == 3:
            return np.asarray(arr, dtype=np.float64)
    if series in data.files:
        raw = np.asarray(data[series], dtype=object)
        if raw.size:
            return np.asarray(raw.reshape(-1)[-1], dtype=np.float64)
    raise KeyError(f"NPZ 中未找到三维状态 {preferred} 或 {series}。")


def surface_from_ca_state(state: np.ndarray, space_z_um: float) -> np.ndarray:
    """由 CA 三维元胞状态提取二维正向腐蚀深度，单位 mm。

    a==1 表示未腐蚀金属；沿 Z 找到第一层金属，层索引乘元胞厚度即为
    从表面向内的正腐蚀深度。没有金属的列取模型最大深度，不改变 XY 尺寸。
    """
    state = np.asarray(state)
    if state.ndim != 3:
        raise ValueError(f"CA 状态必须是三维数组，当前为 {state.shape}。")
    if space_z_um <= 0:
        raise ValueError("space_z_um 必须大于 0。")
    metal = state == 1
    has_metal = np.any(metal, axis=2)
    first_metal = np.argmax(metal, axis=2).astype(np.float64)
    max_depth_layer = state.shape[2] - 1
    depth_layer = np.where(has_metal, first_metal, float(max_depth_layer))
    return depth_layer * float(space_z_um) / 1000.0


def load_simulation_surface(path: str | Path, space_z_um: float) -> np.ndarray:
    """读取 CA-GA NPZ 的最终 perfect_a 并转换为二维表面矩阵。"""
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"模拟 NPZ 文件不存在：{source}")
    with np.load(source, allow_pickle=True) as data:
        state = _load_npz_array(data, "perfect_a", "a_sd")
    return surface_from_ca_state(state, space_z_um)


def save_apdl_mat(matrix: np.ndarray, output: str | Path, variable: str) -> Path:
    """只保存指定的二维 double 变量，生成 APDL 兼容 MAT。"""
    if variable not in {"Z_filled", "F_filled"}:
        raise ValueError("variable 只能是 Z_filled 或 F_filled。")
    arr = _as_numeric_2d(matrix, Path(output))
    destination = Path(output).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    savemat(destination, {variable: arr}, do_compression=False, long_field_names=True)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 APDL 可读取的 Z_filled/F_filled MAT")
    parser.add_argument("--mode", choices=("simulation", "measured"), required=True,
                        help="simulation 读取 CA-GA NPZ；measured 读取已有二维 MAT")
    parser.add_argument("--input", required=True, help="输入 .npz 或 .mat")
    parser.add_argument("--output", required=True, help="输出 .mat 文件")
    parser.add_argument("--variable", choices=("Z_filled", "F_filled"), default=None,
                        help="输出变量；measured 未填写时自动沿用源变量")
    parser.add_argument("--space-z-um", type=float, default=25.0,
                        help="simulation 的 Z 向元胞尺寸，单位 μm，默认 25")
    parser.add_argument("--input-variable", default=None,
                        help="measured 模式下强制读取的源变量名")
    args = parser.parse_args(argv)

    if args.mode == "simulation":
        variable = args.variable or "F_filled"
        matrix = load_simulation_surface(args.input, args.space_z_um)
    else:
        source_variable, matrix = load_measured_matrix(args.input, args.input_variable)
        variable = args.variable or source_variable

    output = save_apdl_mat(matrix, args.output, variable)
    print(f"已生成: {output}")
    print(f"变量: {variable}; 尺寸: {matrix.shape[0]} x {matrix.shape[1]}")
    print(f"范围: [{matrix.min():.6g}, {matrix.max():.6g}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

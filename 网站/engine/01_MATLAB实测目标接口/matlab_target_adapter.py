"""读取原 MATLAB 导出的六列原始目标；GA 内核仍按原高速版合并为四项误差。"""
from pathlib import Path
import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POINTER = ROOT / "实测目标" / "latest_original_target.txt"
# DEFAULT_POINTER = Path(
#     r"E:\CODEX文件\python腐蚀代码\腐蚀代码7_高速版_MATLAB实测接口\实测目标\C17_100d_z\matlab_target.mat"
# )                                                                                                 

UPSTREAM_POINTER = DEFAULT_POINTER

def load_matlab_stage_data(pointer=DEFAULT_POINTER):
    pointer = Path(pointer)
    # 允许批量运行时直接指定某个 matlab_target.mat；不再依赖共享的 latest 指针。
    if pointer.suffix.lower() == ".mat":
        source = pointer
    else:
        if UPSTREAM_POINTER.is_file():
            upstream = UPSTREAM_POINTER.read_text(encoding="utf-8").strip()
            if upstream:
                pointer.parent.mkdir(parents=True, exist_ok=True)
                if not pointer.is_file() or pointer.read_text(encoding="utf-8").strip() != upstream:
                    pointer.write_text(upstream + "\n", encoding="utf-8")
        if not pointer.is_file():
            raise FileNotFoundError(f"未找到 MATLAB 目标指针：{pointer}")
        source = Path(pointer.read_text(encoding="utf-8").strip())
    if not source.is_file():
        raise FileNotFoundError(f"MATLAB 目标文件不存在：{source}")
    mat = loadmat(source, simplify_cells=True)
    target = np.asarray(mat.get("target_data"), dtype=float).reshape(-1)
    if target.shape != (6,) or not np.isfinite(target).all():
        raise ValueError("MATLAB目标必须保留原高速版的六列原始统计量。")
    return target[None, :], source

if __name__ == "__main__":
    data, source = load_matlab_stage_data()
    print(f"来源：{source}")
    print(f"六列原始目标：{data.tolist()}")
    print("GA最终仍由原高速版 combine_objectives 合并为四项误差。")

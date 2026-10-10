"""第二步：从拉伸曲线自动提取名义断裂应变。

支持两种曲线文件格式：
1. ``strain,response``：第一列已经是名义应变，第二列是荷载或应力；
2. ``displacement,load``：需要通过 ``--gauge-length`` 换算应变=位移/标距。

断裂起始点采用峰值后的持续突降判据：响应低于峰值乘以 ``drop-ratio``，并连续
满足 ``sustain-points`` 个采样点。实际试验应检查生成的诊断 CSV 和曲线图。
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import numpy as np

from unified_config import FRACTURE_CONFIG, PATH_CONFIG


def load_curve_csv(path: str | Path, gauge_length: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """读取两列 CSV；支持带表头的 strain,response 或 displacement,load。"""
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError(f"曲线文件为空: {path.name}")
    values: list[tuple[float, float]] = []
    for row in rows:
        if len(row) < 2:
            continue
        try:
            values.append((float(row[0]), float(row[1])))
        except ValueError:
            continue
    if len(values) < 5:
        raise ValueError(f"曲线文件 {path.name} 至少需要 5 个有效数据点")
    array = np.asarray(values, dtype=np.float64)
    x, response = array[:, 0], array[:, 1]
    finite = np.isfinite(x) & np.isfinite(response)
    x, response = x[finite], response[finite]
    if gauge_length is not None:
        if gauge_length <= 0:
            raise ValueError("gauge_length 必须为正数")
        x = x / float(gauge_length)
    order = np.argsort(x, kind="stable")
    return x[order], response[order]


def extract_fracture_strain(
    strain: np.ndarray,
    response: np.ndarray,
    drop_ratio: float = 0.10,
    sustain_points: int = 3,
) -> tuple[float, int]:
    """返回断裂应变和断裂点索引。

    默认定义：峰值之后，响应相对峰值下降至少 10%，并连续保持 3 个点。
    如果没有明显突降，则退回到最大应变点，并在结果中保留该索引供检查。
    """
    strain = np.asarray(strain, dtype=np.float64).reshape(-1)
    response = np.asarray(response, dtype=np.float64).reshape(-1)
    if strain.size != response.size or strain.size < 5:
        raise ValueError("strain 和 response 长度必须一致且至少有 5 个点")
    if not (0 < drop_ratio < 1) or sustain_points < 1:
        raise ValueError("drop_ratio 必须在 0 到 1 之间，sustain_points 必须为正整数")
    peak_index = int(np.argmax(response))
    threshold = response[peak_index] * (1.0 - float(drop_ratio))
    end = strain.size - int(sustain_points) + 1
    fracture_index = None
    for index in range(peak_index + 1, max(peak_index + 1, end)):
        if np.all(response[index:index + sustain_points] <= threshold):
            fracture_index = index
            break
    if fracture_index is None:
        fracture_index = int(np.argmax(strain))
    return float(strain[fracture_index]), fracture_index


def extract_from_metadata(
    metadata_path: str | Path,
    curves_dir: str | Path,
    output_path: str | Path,
    gauge_length: float | None = None,
    drop_ratio: float = 0.10,
    sustain_points: int = 3,
) -> list[dict[str, float | str | int]]:
    """按 metadata.csv 批量提取，并写出 fracture_test_data.csv。"""
    results: list[dict[str, float | str | int]] = []
    curves_dir = Path(curves_dir)
    with Path(metadata_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"sample_id", "curve_file", "ds", "lambda_rho"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"曲线元数据缺少列: {', '.join(sorted(missing))}")
        rows = list(reader)
    if len(rows) < 10:
        raise ValueError(f"曲线元数据至少需要 10 组，当前只有 {len(rows)} 组")
    for row_number, row in enumerate(rows, start=1):
        curve_path = curves_dir / row["curve_file"]
        strain, response = load_curve_csv(curve_path, gauge_length=gauge_length)
        epsilon, index = extract_fracture_strain(strain, response, drop_ratio, sustain_points)
        results.append({
            "sample_id": row["sample_id"], "ds": float(row["ds"]),
            "lambda_rho": float(row["lambda_rho"]), "epsilon_n_f": epsilon,
            "fracture_index": index, "curve_file": row["curve_file"],
        })
        print(f"[{row_number}/{len(rows)}] {row['sample_id']}: epsilon_n_f={epsilon:.8g}")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample_id", "ds", "lambda_rho", "epsilon_n_f"])
        writer.writeheader()
        writer.writerows({key: item[key] for key in writer.fieldnames} for item in results)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="从拉伸曲线提取10组名义断裂应变")
    parser.add_argument("--metadata", type=Path, default=Path(PATH_CONFIG["curve_metadata"]))
    parser.add_argument("--curves-dir", type=Path, default=Path(PATH_CONFIG["curves_dir"]))
    parser.add_argument("--output", type=Path, default=Path(PATH_CONFIG["fracture_test_data"]))
    parser.add_argument("--gauge-length", type=float, default=None, help="位移-荷载文件的标距；应变-荷载文件不填写")
    parser.add_argument("--drop-ratio", type=float, default=float(FRACTURE_CONFIG["curve_drop_ratio"]))
    parser.add_argument("--sustain-points", type=int, default=int(FRACTURE_CONFIG["curve_sustain_points"]))
    args = parser.parse_args()
    started = time.perf_counter()
    extract_from_metadata(args.metadata, args.curves_dir, args.output, args.gauge_length, args.drop_ratio, args.sustain_points)
    print(f"第二步完成，总耗时: {time.perf_counter() - started:.3f} s")


if __name__ == "__main__":
    main()

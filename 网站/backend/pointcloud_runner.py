"""Run the copied MATLAB point-cloud workflow with task-local inputs."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from .pointcloud_config import validate_pointcloud_config

MATLAB_DIR = Path(__file__).resolve().parents[1] / "matlab"
POINT_EXTENSIONS = {".txt", ".csv", ".xyz", ".tsv"}


def inspect_xyz(path: Path) -> dict:
    started = time.perf_counter()
    path = Path(path)
    if path.suffix.lower() not in POINT_EXTENSIONS:
        raise ValueError("点云仅接受 TXT、CSV、TSV、XYZ 文件")
    minima = [math.inf, math.inf, math.inf]
    maxima = [-math.inf, -math.inf, -math.inf]
    count, first_nonempty = 0, True
    sample_points = []
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_no, line in enumerate(stream, 1):
            cells = next(csv.reader([line])) if "," in line else line.split()
            if not line.strip():
                continue
            if len(cells) < 3:
                if not line.strip():
                    continue
                raise ValueError(f"第{line_no}行少于XYZ三列")
            try:
                xyz = [float(item) for item in cells[:3]]
            except ValueError as exc:
                if first_nonempty and all(not any(char.isdigit() for char in cell) for cell in cells[:3]):
                    first_nonempty = False
                    continue
                raise ValueError(f"第{line_no}行XYZ不是数字") from exc
            if not all(math.isfinite(item) for item in xyz):
                raise ValueError(f"第{line_no}行含NaN或无穷值")
            count += 1
            first_nonempty = False
            if len(sample_points) < 1000:
                sample_points.append(xyz)
            else:
                # 均匀确定性蓄水采样，仅作真实点云预览，不参与科学计算。
                # LCG 哈希截断后再取余，避免与科学运行的随机数状态交互。
                slot = ((count * 2654435761) & 0xFFFFFFFF) % count
                if slot < 1000:
                    sample_points[slot] = xyz
            for index, item in enumerate(xyz):
                minima[index] = min(minima[index], item)
                maxima[index] = max(maxima[index], item)
    if count < 3:
        raise ValueError("点云至少需要3个有效XYZ点")
    return {"points": count, "minimum": minima, "maximum": maxima,
            "size_mm": [maxima[0] - minima[0], maxima[1] - minima[1]],
            "sample_points": sample_points, "sample_only": count > len(sample_points),
            "reading_seconds": round(time.perf_counter() - started, 6)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_pointcloud(
    job_dir: Path, reference: Path, detail: Path, config: dict,
    *, matlab_bin: Path | None = None,
) -> dict:
    overrides = validate_pointcloud_config(config)
    if matlab_bin is None:
        located = os.environ.get("MATLAB_BIN") or shutil.which("matlab")
        matlab_bin = Path(located) if located else None
    if matlab_bin is None or not matlab_bin.is_file():
        raise RuntimeError("未找到 MATLAB；请安装 MATLAB 并设置 MATLAB_BIN 为 matlab.exe 的完整路径")
    started = time.perf_counter()
    reference_info = inspect_xyz(reference)
    detail_info = inspect_xyz(detail)
    read_seconds = time.perf_counter() - started
    job_dir = Path(job_dir)
    output = job_dir / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    config_path = job_dir / "pointcloud_config.json"
    config_path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
    environment = os.environ.copy()
    environment.update({
        "CORROSION_CONFIG_JSON": str(config_path.resolve()),
        "CORROSION_SCAN_REFERENCE": str(Path(reference).resolve()),
        "CORROSION_SCAN_DETAIL": str(Path(detail).resolve()),
        "CORROSION_TASK_ROOT": str(job_dir.resolve()),
        "CORROSION_OUTPUT_BASE": str(output.resolve()),
        "CORROSION_DATA_NAME": "pointcloud",
    })
    matlab_script = str((MATLAB_DIR / "untitled.m").resolve()).replace("'", "''").replace("\\", "/")
    command = [str(matlab_bin), "-batch", f"run('{matlab_script}')"]
    with (job_dir / "run.log").open("w", encoding="utf-8", errors="replace") as log:
        completed = subprocess.run(command, cwd=MATLAB_DIR, env=environment,
                                   stdout=log, stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        tail = (job_dir / "run.log").read_text(encoding="utf-8", errors="replace")[-3000:]
        raise RuntimeError(f"MATLAB 点云流程失败（退出码{completed.returncode}）：{tail}")
    target_file = output / "pointcloud" / "matlab_target.mat"
    if not target_file.is_file():
        raise RuntimeError("MATLAB 已结束，但没有生成 matlab_target.mat；请检查任务日志")
    data = loadmat(target_file, simplify_cells=True)
    metrics = np.asarray(data.get("target_data"), dtype=float).reshape(-1)
    issues = data.get("calibration_issues", [])
    if isinstance(issues, str):
        issues = [issues]
    summary = {
        "reference": reference_info, "detail": detail_info,
        "reference_sha256": _sha256(reference), "detail_sha256": _sha256(detail),
        "reading_seconds": round(read_seconds, 3),
        "total_seconds": round(time.perf_counter() - started, 3),
        "six_metrics": [float(item) if math.isfinite(item) else None for item in metrics],
        "calibration_ready": bool(data.get("calibration_ready", False)),
        "calibration_issues": [str(item) for item in np.atleast_1d(issues)],
        "files": [str(path.relative_to(output)).replace("\\", "/")
                  for path in output.rglob("*") if path.is_file()],
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary

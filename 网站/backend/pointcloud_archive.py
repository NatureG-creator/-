"""Archive completed measured-point-cloud results into a user-facing folder."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path


DEFAULT_ARCHIVE_ROOT = Path(r"D:\research\DATA\Point cloud extraction")
CATEGORIES = {
    "reference": "01_参考点云",
    "detail": "02_腐蚀细节点云",
    "metrics": "03_MATLAB六指标",
    "plots": "04_过程图",
    "diagnostics": "05_诊断报告",
    "raw": "06_原始任务包",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".tif", ".tiff"}
DIAGNOSTIC_NAMES = {
    "summary.json", "timing.json", "matlab_timing.json", "diagnostics.json",
    "calibration.json", "manifest.json", "归档清单.json",
}


def archive_root_from_environment() -> Path:
    """Return the configured archive root, with the requested Windows path as default."""
    value = os.environ.get("CORROSION_POINTCLOUD_ARCHIVE", "").strip()
    return Path(value) if value else DEFAULT_ARCHIVE_ROOT


def _copy(source: Path, destination: Path) -> int:
    if not source.is_file():
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return 1


def _output_category(relative: Path) -> str:
    name = relative.name.lower()
    if relative.suffix.lower() in IMAGE_SUFFIXES:
        return "plots"
    if name in DIAGNOSTIC_NAMES or "diagnostic" in name or "calibration" in name:
        return "diagnostics"
    return "metrics"


def archive_pointcloud_job(job_dir: Path, archive_root: Path | None = None, *, job_id: str | None = None) -> dict:
    """Copy one completed point-cloud task into category folders.

    The task-local output remains the source of truth. This function is deliberately
    idempotent: rerunning it for the same task refreshes the same archive directory.
    """
    job_dir = Path(job_dir).resolve()
    archive_root = Path(archive_root or archive_root_from_environment()).expanduser()
    archive_root_resolved = archive_root.resolve()
    job_id = job_id or job_dir.name
    task_folder = archive_root / str(job_id)
    started = time.perf_counter()
    copied: list[dict] = []
    try:
        for category in CATEGORIES.values():
            (task_folder / category).mkdir(parents=True, exist_ok=True)

        inputs = job_dir / "inputs"
        for label, category in (("reference", "reference"), ("detail", "detail")):
            for source in sorted(inputs.glob(f"{label}.*")):
                target = task_folder / CATEGORIES[category] / source.name
                _copy(source, target)
                copied.append({"source": str(source), "destination": str(target), "category": CATEGORIES[category]})

        outputs = job_dir / "outputs"
        if outputs.is_dir():
            for source in sorted(path for path in outputs.rglob("*")
                                 if path.is_file() and path.suffix != ".tmp"
                                 and not path.resolve().is_relative_to(archive_root_resolved)):
                relative = source.relative_to(outputs)
                category = _output_category(relative)
                target = task_folder / CATEGORIES[category] / relative
                _copy(source, target)
                copied.append({"source": str(source), "destination": str(target), "category": CATEGORIES[category]})

        # Keep a complete, reproducible copy of the task inputs, specification, logs,
        # and outputs in addition to the human-oriented category folders.
        raw_root = task_folder / CATEGORIES["raw"]
        for source in sorted(path for path in job_dir.rglob("*") if path.is_file()
                             and not path.resolve().is_relative_to(archive_root_resolved)):
            relative = source.relative_to(job_dir)
            target = raw_root / relative
            _copy(source, target)

        manifest = {
            "schema_version": 1,
            "job_id": str(job_id),
            "archive_root": str(task_folder),
            "created_at": time.time(),
            "file_count": len(copied),
            "categories": CATEGORIES,
            "files": copied,
            "source_task_directory": str(job_dir),
            "elapsed_seconds": round(time.perf_counter() - started, 6),
        }
        manifest_path = task_folder / "归档清单.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"state": "completed", "archive_root": str(task_folder),
                "manifest": str(manifest_path), "file_count": len(copied),
                "elapsed_seconds": manifest["elapsed_seconds"]}
    except (OSError, ValueError, shutil.Error) as exc:
        return {"state": "failed", "archive_root": str(task_folder),
                "error": f"结果归档失败：{exc}",
                "file_count": len(copied),
                "elapsed_seconds": round(time.perf_counter() - started, 6)}


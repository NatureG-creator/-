"""按报告快照生成可缓存的输入包，避免每完成一个方案重压全部数组。"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import threading
import time
import zipfile
import os
from contextlib import contextmanager
from pathlib import Path

from .checkpoint import _atomic_replace, _replace_bytes

_LOCK = threading.Lock()
CSV_FIELDS = ["variant_id", "mode", "label", "state", "pool_policy", "seed", "workers", "threads_per_worker",
              "actual_arch", "first_seconds", "initialization_seconds", "sample_count", "median_seconds",
              "q1_seconds", "q3_seconds", "iqr_seconds", "variation_ratio", "min_seconds", "max_seconds",
              "speedup", "repeat_exact", "process_wall_seconds", "sampled_peak_rss_bytes", "reason"]


@contextmanager
def benchmark_artifact_lock(job_dir, timeout=30.0):
    """Coordinate archive reads and worker cleanup across independent processes."""
    path = Path(job_dir) / ".benchmark_artifacts.lock"
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError) as exc:
                if time.monotonic() >= deadline:
                    raise TimeoutError("等待测速文件读写锁超时，请稍后重试") from exc
                time.sleep(min(.05, max(0.0, deadline-time.monotonic())))
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def report_csv(report):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS + ["exact", "within_tolerance", "samples_seconds"])
    writer.writeheader()
    for row in report.get("rows", []):
        item = {key: row.get(key) for key in CSV_FIELDS}
        item.update({key: row.get("comparison", {}).get(key) for key in ("exact", "within_tolerance")})
        item["samples_seconds"] = json.dumps(row.get("samples_seconds", []))
        writer.writerow(item)
    return buffer.getvalue().encode("utf-8-sig")


def _portable_request(path, job_dir):
    """Rewrite only the job-owned frozen snapshot reference in archived JSON."""
    value = json.loads(path.read_text(encoding="utf-8"))
    source = value.get("initial_state_path")
    if source:
        expected = (job_dir / "inputs" / "initial_state.npz").resolve()
        requested = Path(source)
        requested = requested.resolve() if requested.is_absolute() else (job_dir / requested).resolve()
        root = job_dir.resolve()
        if requested != expected or not expected.is_relative_to(root) or expected.parent != (root / "inputs"):
            raise ValueError("仅允许打包本任务 inputs/initial_state.npz 初始快照")
        if not expected.is_file():
            raise ValueError("本任务冻结初始快照不存在")
        value["initial_state_path"] = "inputs/initial_state.npz"
        return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"), expected
    return path.read_bytes(), None


_BUNDLE_README = """# 测速输入与结果归档

本包保存报告快照、冻结输入、方案日志，以及按设置保留的数组和图片。
所有 JSON 中的 `inputs/initial_state.npz` 相对路径均以解压目录为根解析；
运行时请先将相对路径解析为绝对路径。来源快照的 SHA 与元数据保持原值。

本包不包含科学引擎和 Python 依赖环境，不能作为独立运行程序。
复现时需要使用同版本网站及科学引擎环境，按冻结配置重建测速任务，
并将包内初始快照作为任务来源输入。summary.json 保留生成归档时的报告原始字节。
"""


def ensure_benchmark_bundle(job_dir):
    job_dir = Path(job_dir)
    output, archives = job_dir / "outputs", job_dir / "archives"
    with _LOCK, benchmark_artifact_lock(job_dir):
        report_bytes = (output / "summary.json").read_bytes()
        report = json.loads(report_bytes)
        paths = [output / "benchmark_inputs.json"]
        for row in report.get("rows", []):
            name = row.get("variant_id", row.get("mode", ""))
            if Path(name).name != name or not name:
                raise ValueError("方案目录无效")
            folder = output / "trials" / name
            paths.extend(path for path in sorted(folder.rglob("*"))
                         if path.is_file() and path.suffix != ".tmp" and path.resolve().is_relative_to(output.resolve()))
        portable = {}
        snapshot = None
        for path in paths:
            if path == output / "benchmark_inputs.json" or path.name == "trial_request.json":
                portable[path], referenced = _portable_request(path, job_dir)
                if referenced is not None:
                    snapshot = referenced
        digest = hashlib.sha256(b"portable-snapshot-v2\0" + report_bytes)
        for path in paths:
            stat = path.stat()
            digest.update(f"{path.relative_to(output)}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8"))
        if snapshot is not None:
            stat = snapshot.stat()
            digest.update(f"inputs/initial_state.npz:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8"))
        identity = digest.hexdigest()
        archives.mkdir(exist_ok=True)
        destination = archives / f"benchmark_bundle.{identity}.zip"
        if destination.is_file():
            return destination
        temporary = destination.with_suffix(".tmp")
        started = time.perf_counter()
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                archive.writestr("summary.json", report_bytes)
                archive.writestr("benchmark_results.csv", report_csv(report))
                archive.writestr("README.md", _BUNDLE_README.encode("utf-8"))
                if snapshot is not None:
                    archive.write(snapshot, "inputs/initial_state.npz")
                for path in paths:
                    name = path.relative_to(output).as_posix()
                    if path in portable:
                        archive.writestr(name, portable[path])
                    else:
                        archive.write(path, name)
            _atomic_replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        info = {"report_sha256": hashlib.sha256(report_bytes).hexdigest(), "archive_id": identity,
                "packing_seconds": time.perf_counter() - started, "bytes": destination.stat().st_size,
                "created_at": time.time(), "scope_note": "打包在请求下载时执行；packing_seconds不包含在计算耗时中。"}
        _replace_bytes(output / "bundle_info.json", json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8"))
        return destination

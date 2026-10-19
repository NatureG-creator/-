"""Read-only extraction of raw MAPDL evidence from an existing task."""
from pathlib import Path


def _tail(path: Path, limit=100):
    if not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except OSError:
        return []


def raw_apdl_diagnostics(service, job_id):
    job = service.get_job(job_id)
    if job.get("kind") != "apdl_tension":
        raise ValueError("仅 APDL 任务支持原始求解诊断")
    root = (service.runtime / "jobs" / job_id).resolve()
    if not root.is_dir():
        raise ValueError("任务目录不存在")
    logs = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        name = path.name.lower()
        if name.endswith((".out", ".err", ".log")) or name in {"worker.log", "mapdl.out"}:
            lines = _tail(path)
            errors = [line for line in lines if "*** error" in line.lower() or "error:" in line.lower()]
            warnings = [line for line in lines if "*** warning" in line.lower() or "warning:" in line.lower()]
            logs.append({"name": str(path.relative_to(root)), "errors": errors[-20:], "warnings": warnings[-20:], "tail": lines})
    logs.sort(key=lambda item: item["name"])
    return {"job_id": job_id, "exit_code": job.get("result", {}).get("exit_code") or job.get("exit_code"),
            "first_error": next((line for item in logs for line in item["errors"]), None),
            "first_warning": next((line for item in logs for line in item["warnings"]), None), "logs": logs}

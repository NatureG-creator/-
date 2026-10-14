"""Bootstrap helpers for running the corrosion workflows with Taichi enabled."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def ensure_taichi_runtime() -> None:
    """Re-exec into the bundled Python runtime when the active interpreter lacks Taichi.

    The IDE's `.venv` in this workspace is Python 3.11 and does not have Taichi
    installed. The bundled Codex runtime ships Python 3.12 with Taichi, so we
    transparently jump there before importing any project modules that depend on
    Taichi.
    """
    if os.environ.get("CORROSION_RUNTIME_BOOTSTRAPPED") == "1":
        return

    try:
        import taichi  # noqa: F401

        return
    except Exception:
        pass

    # 网站副本必须跨电脑运行；不使用原开发机的绝对路径。
    configured_python = os.environ.get("CODEX_BUNDLED_PYTHON")
    if not configured_python:
        return
    bundled_python = Path(configured_python).expanduser()
    if not bundled_python.exists():
        return

    if len(sys.argv) == 0 or sys.argv[0] in {"-c", "-m"}:
        return

    current = Path(sys.executable)
    if current.resolve() == bundled_python.resolve():
        return

    for key in ("VIRTUAL_ENV", "PYTHONHOME", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"):
        os.environ.pop(key, None)
    os.environ["CORROSION_RUNTIME_BOOTSTRAPPED"] = "1"
    completed = subprocess.run([str(bundled_python), *sys.argv], check=False)
    raise SystemExit(completed.returncode)

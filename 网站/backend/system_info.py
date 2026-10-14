"""本机环境检查，不启动计算或修改环境。"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2026.10.14"


def process_alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            result = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(result))) and result.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


def find_matlab() -> str | None:
    configured = os.environ.get("MATLAB_BIN")
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which("matlab")
    if found:
        return found
    for base in (Path("C:/Program Files/MATLAB"), Path("D:/learningapp"),
                 Path("F:/matlab"), Path("G:/matlab")):
        if base.is_dir():
            candidates = sorted([*base.glob("*/bin/matlab.exe"), *base.glob("bin/matlab.exe")],
                                reverse=True)
            if candidates:
                return str(candidates[0])
    return None


def capabilities() -> dict:
    matlab = find_matlab()
    return {"matlab": bool(matlab), "matlab_path": matlab,
            "taichi": importlib.util.find_spec("taichi") is not None,
            "python": sys.version.split()[0], "python_path": sys.executable,
            "local_only": True, "resume_backend": "NumPy", "version": VERSION}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_record(path: Path, default=None):
    import json
    if not Path(path).is_file():
        return default
    return json.loads(Path(path).read_text(encoding="utf-8"))

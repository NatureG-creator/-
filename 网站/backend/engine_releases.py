"""Bind new CPU simulations to immutable releases; legacy jobs stay original."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def _read(path, default=None):
    if not Path(path).exists():
        return default
    # Windows can briefly deny reads during an atomic profile replacement.
    for attempt in range(5):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(.02)


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _release_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value):
        raise ValueError("计算引擎版本标识无效")
    return value


def binding(job_dir):
    value = _read(Path(job_dir) / "engine_binding.json", {"release_id": "original"})
    _release_id(value["release_id"])
    return value


def worker_root(job_dir, runtime, original_root):
    release_id = binding(job_dir)["release_id"]
    if release_id == "original":
        return Path(original_root)
    return Path(runtime) / "engine_releases" / release_id / "site"


def profile(runtime, original_root, bound):
    release_id = _release_id(bound["release_id"])
    if release_id == "original":
        return {"release_id": release_id, "label": "原版 NumPy", "root": str(original_root), "python": sys.executable}
    release = Path(runtime) / "engine_releases" / release_id
    manifest_path = release / "manifest.json"
    raw = manifest_path.read_bytes()
    if bound.get("manifest_sha256") and hashlib.sha256(raw).hexdigest() != bound["manifest_sha256"]:
        raise ValueError("任务绑定的引擎清单已改变，拒绝切换实现")
    manifest = json.loads(raw)
    if manifest["release_id"] != release_id:
        raise ValueError("引擎清单版本不一致")
    root = (release / "site").resolve()
    for name, expected in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"计算引擎文件已改变：{name}")
    interpreter = release / "venv/Scripts/python.exe" if os.name == "nt" else release / "venv/bin/python"
    if not interpreter.is_file():
        raise ValueError("引擎专用 Python 不存在")
    return {"release_id": release_id, "label": manifest["label"], "root": str(root), "python": str(interpreter),
            "manifest_sha256": hashlib.sha256(raw).hexdigest()}


def active_release(runtime):
    return _release_id(_read(Path(runtime) / "active_engine.json", {"release_id": "original"})["release_id"])


def freeze_binding(job_dir, spec, runtime, original_root):
    release_id = "original"
    if spec.get("kind") == "simulation" and spec.get("config", {}).get("mode") == "pycharm":
        release_id = spec["engine_release"] if "engine_release" in spec else active_release(runtime)
    elif spec.get("engine_release", "original") != "original":
        raise ValueError("Numba 扫描＋扩散只支持 PyCharm CPU 多进程模式")
    selected = profile(runtime, original_root, {"release_id": release_id})
    bound = {"version": 1, "release_id": selected["release_id"], "label": selected["label"],
             "created_at": time.time()}
    if "manifest_sha256" in selected:
        bound["manifest_sha256"] = selected["manifest_sha256"]
    path = Path(job_dir) / "engine_binding.json"
    if path.exists():
        raise ValueError("任务引擎已经冻结，不能重新绑定")
    _write(path, bound)
    return bound


def launch_profile(job_dir, runtime, original_root):
    return profile(runtime, original_root, binding(job_dir))


def precheck_bound_job(spec, job_dir, runtime, original_root):
    selected = launch_profile(job_dir, runtime, original_root)
    if selected["release_id"] == "original":
        from .runner import precheck_resume
        return precheck_resume(spec, job_dir)
    script = ("import json,sys;from pathlib import Path;from backend.runner import precheck_resume;"
              "p=Path(sys.argv[1]);s=json.loads((p/'spec.json').read_text(encoding='utf-8'));"
              "print(json.dumps(precheck_resume(s,p)))")
    result = subprocess.run([selected["python"], "-c", script, str(Path(job_dir).resolve())],
                            cwd=selected["root"], capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=45,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode != 0:
        raise ValueError("绑定引擎恢复预检失败：" + result.stderr[-3000:])
    return json.loads(result.stdout.strip().splitlines()[-1])


def activate(runtime, original_root, release_id):
    selected = profile(runtime, original_root, {"release_id": release_id})
    path = Path(runtime) / "active_engine.json"
    if path.exists():
        _write(path.with_name("active_engine.previous.json"), _read(path))
    value = {"release_id": selected["release_id"], "label": selected["label"], "activated_at": time.time()}
    _write(path, value)
    return value


def recover_handoff_queue(service, original_root):
    """Adopt only the queued IDs captured by the controlled service handoff."""
    path = service.runtime / "service_handoff.json"
    handoff = _read(path)
    if not handoff or handoff.get("adopted_by") or handoff.get("site_root") != str(original_root):
        return
    from .system_info import json_record, process_alive
    if process_alive(handoff.get("previous_server_pid")):
        return
    for job_id in handoff.get("queued_jobs", []):
        service.validate_id(job_id)
        folder = service.runtime / "jobs" / job_id
        state = json_record(folder / "status.json", {})
        if state.get("state") == "queued" and not process_alive(state.get("pid")):
            service.pending_jobs.add(job_id)
            service.launch(job_id)
    handoff.update(adopted_by=os.getpid(), adopted_at=time.time())
    _write(path, handoff)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--activate", required=True)
    args = parser.parse_args()
    print(json.dumps(activate(args.runtime, Path(__file__).resolve().parents[1], args.activate), ensure_ascii=False))

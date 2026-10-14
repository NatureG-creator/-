"""Local-only HTTP API and static workbench."""

from __future__ import annotations

import json
import mimetypes
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .config import default_simulation_config, validate_simulation_config, validate_targets
from .pointcloud_config import catalog, validate_pointcloud_config
from .pointcloud_runner import POINT_EXTENSIONS, inspect_xyz
from .runner import _atomic_json
from .targets import inspect_target, load_targets

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
UPLOAD_EXTENSIONS = POINT_EXTENSIONS | {".mat"}
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024


class JobServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, host: str, port: int, runtime: Path):
        self.runtime = Path(runtime)
        self.runtime.mkdir(parents=True, exist_ok=True)
        (self.runtime / "jobs").mkdir(exist_ok=True)
        (self.runtime / "uploads").mkdir(exist_ok=True)
        self.processes: dict[str, subprocess.Popen] = {}
        super().__init__((host, port), Handler)

    def upload(self, name: str, stream, length: int) -> dict:
        extension = Path(name).suffix.lower()
        if extension not in UPLOAD_EXTENSIONS:
            raise ValueError("文件类型仅支持 TXT、CSV、TSV、XYZ、MAT")
        if length < 1 or length > MAX_UPLOAD_BYTES:
            raise ValueError("文件必须非空且不超过1GB")
        upload_id = uuid.uuid4().hex
        folder = self.runtime / "uploads" / upload_id
        folder.mkdir()
        path = folder / f"input{extension}"
        with path.open("wb") as output:
            remaining = length
            while remaining:
                block = stream.read(min(1024 * 1024, remaining))
                if not block:
                    raise ValueError("上传数据不完整")
                output.write(block)
                remaining -= len(block)
        record = {"id": upload_id, "name": Path(name).name, "extension": extension,
                  "bytes": length, "uploaded_at": time.time()}
        _atomic_json(folder / "metadata.json", record)
        return record

    def get_upload(self, upload_id: str) -> tuple[dict, Path]:
        if len(upload_id) != 32 or not all(char in "0123456789abcdef" for char in upload_id):
            raise FileNotFoundError("上传文件编号无效")
        folder = self.runtime / "uploads" / upload_id
        metadata = folder / "metadata.json"
        if not metadata.is_file():
            raise FileNotFoundError("上传文件不存在")
        record = json.loads(metadata.read_text(encoding="utf-8"))
        return record, folder / f"input{record['extension']}"

    def create_job(self, payload: dict) -> dict:
        kind = payload.get("kind")
        if kind not in {"simulation", "pointcloud"}:
            raise ValueError("任务类型必须为 simulation 或 pointcloud")
        job_id = uuid.uuid4().hex[:16]
        job_dir = self.runtime / "jobs" / job_id
        if kind == "simulation":
            config = validate_simulation_config(payload["config"])
            run_mode = payload.get("run_mode", "staged")
            if "upload_id" in payload:
                _, source = self.get_upload(payload["upload_id"])
                targets = load_targets(source, payload.get("variable"))
            else:
                targets = payload.get("targets")
            validate_targets(targets, run_mode)
            config["ACTIVE_STAGE_TARGET_DATA"] = targets
            if run_mode == "single":
                config["SINGLE_STAGE_TARGET_DATA"] = targets[0]
            if payload.get("random_seed"):
                config["GA_CONFIG"]["seed"] = int.from_bytes(os.urandom(4), "big")
            validate_simulation_config(config)
            spec = {"kind": kind, "config": config, "targets": targets, "run_mode": run_mode}
        else:
            reference, ref_path = self.get_upload(payload["reference_id"])
            detail, detail_path = self.get_upload(payload["detail_id"])
            if reference["extension"] not in POINT_EXTENSIONS or detail["extension"] not in POINT_EXTENSIONS:
                raise ValueError("点云任务必须上传文本XYZ文件")
            config = validate_pointcloud_config(payload.get("pointcloud_config", {}))
            spec = {"kind": kind, "reference_id": reference["id"],
                    "detail_id": detail["id"], "reference_extension": reference["extension"],
                    "detail_extension": detail["extension"], "pointcloud_config": config,
                    "reference_preview": inspect_xyz(ref_path), "detail_preview": inspect_xyz(detail_path)}
        job_dir.mkdir()
        _atomic_json(job_dir / "spec.json", spec)
        status = {"id": job_id, "kind": kind, "state": "queued", "created_at": time.time(),
                  "updated_at": time.time(), "pid": None}
        _atomic_json(job_dir / "status.json", status)
        self.launch(job_id)
        return status

    def launch(self, job_id: str) -> None:
        job_dir = self.runtime / "jobs" / job_id
        env = os.environ.copy()
        env["CORROSION_RUNTIME_DIR"] = str(self.runtime.resolve())
        log = (job_dir / "worker.log").open("a", encoding="utf-8")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            [sys.executable, "-m", "backend.worker", job_id], cwd=ROOT, env=env,
            stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
            start_new_session=os.name != "nt",
        )
        log.close()
        self.processes[job_id] = process

    def get_job(self, job_id: str) -> dict:
        if len(job_id) != 16 or not all(char in "0123456789abcdef" for char in job_id):
            raise FileNotFoundError("任务编号无效")
        path = self.runtime / "jobs" / job_id / "status.json"
        if not path.is_file():
            raise FileNotFoundError("任务不存在")
        state = json.loads(path.read_text(encoding="utf-8"))
        process = self.processes.get(job_id)
        if state["state"] in {"queued", "running"} and process is not None and process.poll() is not None:
            state.update(state="interrupted", error="进程已退出；可从已保存的检查点恢复")
            _atomic_json(path, state)
        elif state["state"] == "running" and process is None:
            state.update(state="interrupted", error="服务已重新启动；请检查原任务进程后恢复")
            _atomic_json(path, state)
        state["files"] = self.job_files(job_id)
        return state

    def job_files(self, job_id: str) -> list[dict]:
        root = self.runtime / "jobs" / job_id / "outputs"
        if not root.is_dir():
            return []
        return [{"name": str(path.relative_to(root)).replace("\\", "/"), "bytes": path.stat().st_size}
                for path in root.rglob("*") if path.is_file()]

    def resume(self, job_id: str) -> dict:
        state = self.get_job(job_id)
        spec = json.loads((self.runtime / "jobs" / job_id / "spec.json").read_text(encoding="utf-8"))
        if spec["kind"] != "simulation" or spec["config"]["mode"] != "strict":
            raise ValueError("只有严格可复现模拟支持检查点恢复")
        if state["state"] not in {"interrupted", "failed"}:
            raise ValueError("任务当前不能恢复")
        state.update(state="queued", error=None, updated_at=time.time())
        _atomic_json(self.runtime / "jobs" / job_id / "status.json", state)
        self.launch(job_id)
        return state

    def stop(self, job_id: str) -> dict:
        state = self.get_job(job_id)
        process = self.processes.get(job_id)
        if process is None or process.poll() is not None:
            raise ValueError("当前服务没有可停止的活动进程")
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False,
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        state.update(state="interrupted", error="用户停止任务", updated_at=time.time())
        _atomic_json(self.runtime / "jobs" / job_id / "status.json", state)
        return state


class Handler(BaseHTTPRequestHandler):
    server: JobServer

    def _json(self, status: int, value) -> None:
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 4_000_000:
            raise ValueError("请求数据为空或超过4MB")
        return json.loads(self.rfile.read(length))

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError("文件不存在")
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(path.name)}")
        self.end_headers()
        with path.open("rb") as stream:
            shutil.copyfileobj(stream, self.wfile, 1024 * 1024)

    def _handle(self, method: str) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        parts = [part for part in path.split("/") if part]
        query = parse_qs(parsed.query)
        if method == "GET" and path == "/api/defaults":
            return self._json(200, {"simulation": default_simulation_config(),
                                    "pointcloud": catalog(),
                                    "capabilities": {"matlab": bool(os.environ.get("MATLAB_BIN") or shutil.which("matlab")),
                                                     "taichi": self._has_taichi()}})
        if method == "GET" and path == "/api/jobs":
            ids = sorted((self.server.runtime / "jobs").iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
            return self._json(200, [self.server.get_job(item.name) for item in ids[:50] if item.is_dir()])
        if method == "POST" and path == "/api/uploads":
            name = query.get("name", [""])[0]
            return self._json(201, self.server.upload(name, self.rfile, int(self.headers.get("Content-Length", "0"))))
        if len(parts) == 4 and parts[:2] == ["api", "uploads"] and parts[3] == "inspect" and method == "GET":
            _, source = self.server.get_upload(parts[2])
            kind = query.get("kind", ["target"])[0]
            return self._json(200, inspect_xyz(source) if kind == "pointcloud" else inspect_target(source))
        if method == "POST" and path == "/api/jobs":
            return self._json(201, self.server.create_job(self._body()))
        if len(parts) >= 3 and parts[:2] == ["api", "jobs"]:
            job_id = parts[2]
            if len(parts) == 3 and method == "GET":
                return self._json(200, self.server.get_job(job_id))
            if len(parts) == 4 and parts[3] == "resume" and method == "POST":
                return self._json(200, self.server.resume(job_id))
            if len(parts) == 4 and parts[3] == "stop" and method == "POST":
                return self._json(200, self.server.stop(job_id))
            if len(parts) == 4 and parts[3] == "log" and method == "GET":
                job_dir = self.server.runtime / "jobs" / job_id
                if not (job_dir / "status.json").is_file():
                    raise FileNotFoundError("任务不存在")
                log = job_dir / "worker.log"
                return self._json(200, {"text": log.read_text(encoding="utf-8", errors="replace")[-20000:] if log.exists() else ""})
            if len(parts) >= 5 and parts[3] == "download" and method == "GET":
                root = (self.server.runtime / "jobs" / job_id / "outputs").resolve()
                destination = (root / Path(*parts[4:])).resolve()
                if not destination.is_relative_to(root):
                    raise FileNotFoundError("文件路径无效")
                return self._send_file(destination)
        if method == "GET":
            relative = "index.html" if path == "/" else path.lstrip("/")
            destination = (FRONTEND / relative).resolve()
            if not destination.is_relative_to(FRONTEND.resolve()):
                raise FileNotFoundError("页面路径无效")
            return self._static(destination)
        raise FileNotFoundError("接口不存在")

    @staticmethod
    def _has_taichi() -> bool:
        try:
            import taichi  # noqa: F401
            return True
        except ImportError:
            return False

    def _static(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError("页面不存在")
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(path.name)[0] or "application/octet-stream") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method: str):
        try:
            self._handle(method)
        except (ValueError, KeyError, TypeError) as exc:
            self._json(400, {"error": str(exc)})
        except FileNotFoundError as exc:
            self._json(404, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})


def make_server(host: str = "127.0.0.1", port: int = 8523, runtime: Path | None = None) -> JobServer:
    return JobServer(host, port, runtime or ROOT / ".runtime")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8523)
    args = parser.parse_args()
    server = make_server(args.host, args.port)
    print(f"腐蚀研究网站: http://{args.host}:{server.server_port}/", flush=True)
    server.serve_forever()

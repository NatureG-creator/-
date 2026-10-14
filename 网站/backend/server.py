"""仅本机HTTP接口；MATLAB/Python计算在任务子进程执行。"""

from __future__ import annotations

import json
import mimetypes
import shutil
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import default_simulation_config, validate_simulation_config, validate_targets
from .git_sync import sync_status, sync_website
from .job_service import JobService
from .pointcloud_config import catalog
from .pointcloud_runner import inspect_xyz
from .system_info import ROOT, VERSION, capabilities, json_record
from .targets import inspect_target

FRONTEND = ROOT / "frontend"


class JobServer(JobService, ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, host, port, runtime):
        self.initialize(runtime)
        super().__init__((host, port), Handler)

    def create_batch(self, payload):
        from .batch_service import create_batch
        return create_batch(self, payload)


class Handler(BaseHTTPRequestHandler):
    server: JobServer

    def _json(self, status, value):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 4_000_000:
            raise ValueError("请求数据为空或超过4MB")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("请求数据必须是JSON对象")
        return value

    def _file(self, path, *, download=False):
        if not path.is_file():
            raise FileNotFoundError("文件不存在")
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("X-Content-Type-Options", "nosniff")
        if download:
            self.send_header("Content-Disposition",
                             "attachment; filename*=UTF-8''" + urllib.parse.quote(path.name))
        self.end_headers()
        with path.open("rb") as stream:
            shutil.copyfileobj(stream, self.wfile, 1024 * 1024)

    def _origin_allowed(self):
        host = self.headers.get("Host", "")
        if host not in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}",
                        f"[::1]:{self.server.server_port}"}:
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}", f"https://{host}"}:
            return False
        return True

    def _handle(self, method):
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        parts = [part for part in path.split("/") if part]
        query = urllib.parse.parse_qs(parsed.query)
        if method == "GET" and path == "/api/defaults":
            from .parameter_catalog import simulation_catalog
            return self._json(200, {"simulation": default_simulation_config(),
                                   "simulation_catalog": simulation_catalog(),
                                   "pointcloud": catalog(), "capabilities": capabilities(),
                                   "version": VERSION})
        if method == "GET" and path == "/api/health":
            return self._json(200, {"service": "corrosion-research-workbench", "version": VERSION,
                                   "site_root": str(ROOT), "capabilities": capabilities()})
        if path == "/api/sync":
            return self._json(200, sync_status() if method == "GET" else sync_website())
        if method == "POST" and path == "/api/config/validate":
            from .parameter_catalog import estimate_resources
            body = self._body()
            config = validate_simulation_config(body["config"])
            targets = body.get("targets") or (
                [config["SINGLE_STAGE_TARGET_DATA"]] if body.get("run_mode") == "single"
                else config["ACTIVE_STAGE_TARGET_DATA"])
            validate_targets(targets, body.get("run_mode", "staged"))
            return self._json(200, {"config": config,
                                   "resources": estimate_resources(config, len(targets), body.get("run_mode", "staged")),
                                   "issues": []})
        if method == "GET" and path == "/api/jobs":
            folders = sorted((self.server.runtime / "jobs").iterdir(),
                             key=lambda item: item.stat().st_mtime, reverse=True)
            folders = [item for item in folders if item.is_dir() and (item / "status.json").is_file()
                       and len(item.name) == 16 and all(char in "0123456789abcdef" for char in item.name)]
            return self._json(200, [self.server.get_job(item.name) for item in folders[:100]])
        if method == "POST" and path == "/api/uploads":
            return self._json(201, self.server.upload(query.get("name", [""])[0], self.rfile,
                                                    int(self.headers.get("Content-Length", "0"))))
        if len(parts) == 4 and parts[:2] == ["api", "uploads"] and parts[3] == "inspect" and method == "GET":
            _, source = self.server.get_upload(parts[2])
            if query.get("kind", ["target"])[0] == "pointcloud":
                value = inspect_xyz(source)
            else:
                value = inspect_target(source, query.get("variable", [None])[0],
                                       query.get("orientation", ["auto"])[0])
            return self._json(200, value)
        if method == "POST" and path == "/api/jobs":
            return self._json(201, self.server.create_job(self._body()))
        if method == "POST" and path == "/api/batches":
            return self._json(201, self.server.create_batch(self._body()))
        if len(parts) == 3 and parts[:2] == ["api", "batches"] and method == "GET":
            self.server.validate_id(parts[2])
            value = json_record(self.server.runtime / "batches" / parts[2] / "status.json")
            if value is None:
                raise FileNotFoundError("批次不存在")
            value["jobs"] = [self.server.get_job(job_id) for job_id in value["job_ids"]]
            return self._json(200, value)
        if len(parts) >= 3 and parts[:2] == ["api", "jobs"]:
            job_id = self.server.validate_id(parts[2])
            folder = self.server.runtime / "jobs" / job_id
            if len(parts) == 3 and method == "GET":
                return self._json(200, self.server.get_job(job_id))
            if len(parts) == 4 and method == "POST":
                operation = {"resume": self.server.resume, "stop": self.server.stop,
                             "transfer": self.server.transfer}.get(parts[3])
                if operation:
                    return self._json(200, operation(job_id))
            if len(parts) == 4 and parts[3] == "spec" and method == "GET":
                return self._json(200, self.server.get_job(job_id)["spec"])
            if len(parts) == 4 and parts[3] == "log" and method == "GET":
                return self._json(200, {"text": self.server.log_tail(job_id)})
            if len(parts) >= 5 and parts[3] in {"download", "view"} and method == "GET":
                self.server.get_job(job_id)
                root = (folder / "outputs").resolve()
                destination = (root / Path(*parts[4:])).resolve()
                if not destination.is_relative_to(root):
                    raise FileNotFoundError("文件路径无效")
                return self._file(destination, download=parts[3] == "download")
        if method == "GET":
            relative = "index.html" if path == "/" else path.lstrip("/")
            destination = (FRONTEND / relative).resolve()
            if not destination.is_relative_to(FRONTEND.resolve()):
                raise FileNotFoundError("页面路径无效")
            return self._file(destination)
        raise FileNotFoundError("接口不存在")

    def _dispatch(self, method):
        try:
            if not self._origin_allowed():
                return self._json(403, {"error": "本机服务拒绝跨站请求，请从本机网站打开"})
            self._handle(method)
        except (ValueError, KeyError, TypeError) as exc:
            self._json(400, {"error": str(exc)})
        except FileNotFoundError as exc:
            self._json(404, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")


def make_server(host="127.0.0.1", port=8523, runtime=None):
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("研究任务服务仅允许本机访问")
    return JobServer(host, port, runtime or ROOT / ".runtime")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8523)
    args = parser.parse_args()
    server = make_server(port=args.port)
    print(f"腐蚀研究网站：http://127.0.0.1:{server.server_port}/", flush=True)
    server.serve_forever()

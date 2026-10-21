"""仅本机HTTP接口；MATLAB/Python计算在任务子进程执行。"""

from __future__ import annotations

import json
import mimetypes
import os
import shutil
import tempfile
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import (PATH_DIRECTORY_KEYS, PATH_FILE_KEYS, website_default_simulation_config,
                     validate_path_config, validate_simulation_config, validate_targets)
from .git_sync import sync_status, sync_website
from .job_service import JobService
from .pointcloud_config import catalog
from .pointcloud_runner import inspect_xyz
from .service_identity import source_revision
from .system_info import ROOT, VERSION, capabilities, json_record
from .targets import inspect_target

FRONTEND = ROOT / "frontend"
DEFAULT_RUNTIME = Path(os.environ.get("CORROSION_RUNTIME_DIR", r"D:\research\CorrosionWebsiteData"))


class JobServer(JobService, ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, host, port, runtime):
        self.source_revision = source_revision(ROOT)
        self.initialize(runtime)
        super().__init__((host, port), Handler)

    def create_batch(self, payload):
        from .batch_service import create_batch
        return create_batch(self, payload)


class Handler(BaseHTTPRequestHandler):
    server: JobServer

    def log_message(self, format, *args):
        try:
            super().log_message(format, *args)
        except (OSError, AttributeError):
            # pythonw may have no usable console. Logging must not abort HTTP.
            try:
                with (self.server.runtime / 'http.log').open('a', encoding='utf-8') as log:
                    log.write(self.log_date_time_string() + ' ' + (format % args) + '\n')
            except OSError:
                pass

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

    def _file(self, path, *, download=False, download_name=None):
        if not path.is_file():
            raise FileNotFoundError("文件不存在")
        with path.open("rb") as stream:
            # Reports are atomically replaced while jobs run. Bind both length
            # and body to one open snapshot, rather than stat/open by pathname.
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(os.fstat(stream.fileno()).st_size))
            self.send_header("X-Content-Type-Options", "nosniff")
            if download:
                self.send_header("Content-Disposition",
                                 "attachment; filename*=UTF-8''" + urllib.parse.quote(download_name or path.name))
            self.end_headers()
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
            defaults = website_default_simulation_config()
            path_catalog = None
            saved_paths = self.server.runtime / "path_config.json"
            if saved_paths.is_file():
                try:
                    saved = json.loads(saved_paths.read_text(encoding="utf-8"))
                    validate_path_config(saved)
                    defaults["PATH_CONFIG"] = saved
                    path_catalog = saved
                except (OSError, ValueError, json.JSONDecodeError):
                    pass
            parameters = simulation_catalog()
            if path_catalog:
                for item in parameters:
                    if item["group"] == "PATH_CONFIG":
                        item["value"] = path_catalog[item["key"]]
            return self._json(200, {"simulation": defaults,
                                   "simulation_catalog": parameters,
                                   "pointcloud": catalog(), "capabilities": capabilities(),
                                   "version": VERSION})
        if method == "GET" and path == "/api/health":
            return self._json(200, {"service": "corrosion-research-workbench", "version": VERSION,
                                   "source_revision": self.server.source_revision,
                                   "site_root": str(ROOT), "capabilities": capabilities()})
        if method == "GET" and path == "/api/apdl/presets":
            from .apdl_presets import get_presets
            return self._json(200,get_presets())
        if method == "GET" and path == "/api/fitting/catalog":
            from .fitting_service import fitting_catalog
            return self._json(200, fitting_catalog())
        if method == "GET" and path == "/api/origin/capabilities":
            from .origin_plotting import origin_capabilities
            return self._json(200, origin_capabilities())
        if method == "POST" and path == "/api/origin/jobs":
            body = self._body()
            body['kind'] = 'origin_plot'
            return self._json(201, self.server.create_job(body))
        if method == "POST" and len(parts) == 5 and parts[:3] == ["api", "origin", "jobs"] and parts[4] == "open":
            return self._json(200, self.server.open_origin(parts[3]))
        if method == "POST" and path == "/api/fitting/inspect":
            from .fitting_service import inspect_fitting
            return self._json(200, inspect_fitting(self.server, self._body()))
        if method == "POST" and path == "/api/visualization/inspect":
            from .visualization_service import inspect_upload
            return self._json(200, inspect_upload(self.server, self._body()))
        if method == "GET" and path == "/api/visualization/simulation-jobs":
            from .visualization_service import simulation_sources
            return self._json(200, simulation_sources(self.server))
        if method == "POST" and path == "/api/visualization/simulation-stage":
            from .visualization_service import inspect_simulation_stage
            return self._json(200, inspect_simulation_stage(self.server, self._body()))
        if method == "POST" and path == "/api/fitting/precheck":
            from .fitting_service import precheck_fitting
            return self._json(200, precheck_fitting(self.server, self._body()))
        if method == "POST" and path == "/api/fitting/jobs":
            body = self._body()
            body['kind'] = 'fitting'
            return self._json(201, self.server.create_job(body))
        if method == "GET" and path == "/api/apdl/capabilities":
            from .apdl_solver import mapdl_capabilities
            return self._json(200,mapdl_capabilities())
        if method == 'GET' and path == '/api/apdl/stress-strain/sources':
            from .apdl_stress_strain import list_stress_strain_sources
            return self._json(200, list_stress_strain_sources(self.server))
        if method == 'POST' and path == '/api/apdl/stress-strain/comparisons':
            from .apdl_stress_strain import create_stress_strain_comparison
            return self._json(201, create_stress_strain_comparison(self.server, self._body()))
        if method == 'GET' and len(parts) == 5 and parts[:3] == ['api', 'apdl', 'stress-strain-comparisons']:
            from .apdl_stress_strain import comparison_file
            return self._file(comparison_file(self.server, parts[3], parts[4]),
                              download=query.get('download') == ['1'])
        if method == 'GET' and path == '/api/apdl/viewer/jobs':
            from .apdl_viewer import viewer_jobs
            return self._json(200, viewer_jobs(self.server))
        if method == 'POST' and len(parts) == 5 and parts[:3] == ['api', 'apdl', 'jobs'] and parts[4] == 'viewer':
            from .apdl_viewer import open_viewer
            return self._json(200, open_viewer(self.server, parts[3], self._body()))
        if method == 'POST' and len(parts) == 6 and parts[:3] == ['api', 'apdl', 'jobs'] and parts[4:] == ['viewer', 'render']:
            from .apdl_viewer import render_view
            return self._json(200, render_view(self.server, parts[3], self._body()))
        if method == 'GET' and len(parts) == 4 and parts[:3] == ['api', 'apdl', 'viewers']:
            session = self.server.runtime / 'apdl_viewers' / parts[3]
            image = next(session.glob('*.png'), None)
            if image is None:
                raise FileNotFoundError('云图文件不存在')
            return self._file(image)
        if method == 'POST' and path == '/api/apdl/table-inspect':
            from .apdl_materials import uploaded_table
            table, source, _ = uploaded_table(self.server, self._body())
            return self._json(200, dict(table, rows=table['rows'][:20], source=source))
        if method == 'POST' and path == '/api/apdl/material-import':
            from .apdl_materials import import_material
            return self._json(200, import_material(self.server, self._body()))
        if method == 'POST' and path == '/api/apdl/commands/check':
            from .apdl_commands import check_commands
            return self._json(200, check_commands(self.server, self._body()))
        if method == 'POST' and path == '/api/apdl/comparisons':
            from .apdl_analysis import save_comparison
            return self._json(201, save_comparison(self.server, self._body()))
        if method == 'GET' and len(parts) == 5 and parts[:3] == ['api', 'apdl', 'jobs']:
            if parts[4] == 'commands':
                from .apdl_commands import command_snapshot
                return self._json(200, command_snapshot(self.server, parts[3]))
            if parts[4] == 'raw-diagnostics':
                from .apdl_raw_diagnostics import raw_apdl_diagnostics
                return self._json(200, raw_apdl_diagnostics(self.server, parts[3]))
            if parts[4] == 'diagnosis':
                from .apdl_commands import _source
                from .apdl_analysis import diagnose_output
                _, output = _source(self.server, parts[3])
                return self._json(200, diagnose_output(output))
        if method == "POST" and path == "/api/apdl/matlab-convert":
            from .apdl_matlab import convert_uploaded_matrix
            return self._json(200, convert_uploaded_matrix(self.server, self._body()))
        if method == "GET" and len(parts) == 5 and parts[:3] == ["api", "uploads", "inspect"] and parts[4] == "mat":
            from .apdl_matlab import inspect_mat_variables
            _, source = self.server.get_upload(parts[2])
            return self._json(200, {"variables": inspect_mat_variables(source)})
        if method == "POST" and path == "/api/apdl/precheck":
            from .apdl_service import precheck_apdl
            return self._json(200,precheck_apdl(self.server,self._body()))
        if len(parts)==5 and parts[:3]==['api','apdl','jobs'] and parts[4]=='reload-config' and method=='POST':
            from .apdl_reload import reload_apdl_config
            return self._json(200,reload_apdl_config(self.server,parts[3]))
        if method == "POST" and path == "/api/apdl/jobs":
            body=self._body()
            body['kind']='apdl_tension'
            return self._json(201,self.server.create_job(body))
        if method == "POST" and path == "/api/benchmarks":
            body = self._body()
            body["kind"] = "benchmark"
            return self._json(201, self.server.create_job(body))
        if method == "POST" and path == "/api/benchmark-diagnostics":
            body = self._body()
            body["kind"] = "diagnostics"
            return self._json(201, self.server.create_job(body))
        if method == "POST" and path == "/api/benchmarks/precheck":
            from .benchmark import build_variants
            spec, _ = self.server.benchmark_spec(self._body())
            return self._json(200, {"options": spec["options"], "variants": build_variants(spec),
                "estimated_host_array_bytes": spec["estimated_host_array_bytes"], "estimated_work": spec["estimated_work"],
                "stage_number": spec.get("stage_number", 1), "initial_state_info": spec.get("initial_state_info"),
                "scope_note": spec["scope_note"], "issues": []})
        if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "benchmarks"] and parts[3] == "retry":
            return self._json(201, self.server.retry_benchmark(parts[2], self._body()))
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
        if method == "POST" and path == "/api/paths/apply":
            body = self._body()
            paths = validate_path_config(body.get("PATH_CONFIG"))
            created = []
            for key in PATH_DIRECTORY_KEYS:
                target = Path(paths[key]).expanduser()
                target.mkdir(parents=True, exist_ok=True)
                created.append(str(target.resolve()))
            for key in PATH_FILE_KEYS:
                parent = Path(paths[key]).expanduser().parent
                parent.mkdir(parents=True, exist_ok=True)
                created.append(str(parent.resolve()))
            saved = {key: str(Path(value).expanduser().resolve()) for key, value in paths.items()}
            path_file = self.server.runtime / "path_config.json"
            path_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = path_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, path_file)
            from .config import source_config
            source_config.PATH_CONFIG.clear()
            source_config.PATH_CONFIG.update({key: Path(value) for key, value in saved.items()})
            return self._json(200, {"PATH_CONFIG": saved, "created_directories": sorted(set(created))})
        if method == 'POST' and path == '/api/jobs/delete-batch':
            from .job_history import delete_jobs
            body=self._body()
            return self._json(200, delete_jobs(self.server, body.get('job_ids'), body.get('confirm_job_ids')))
        if method == "GET" and path == "/api/jobs":
            # Existing data-source selectors still see hidden task results.
            return self._json(200, self.server.list_jobs(
                include_hidden=query.get('include_hidden', ['1'])[0] != '0'))
        if method == 'POST' and path == '/api/local-directory':
            from .task_io import choose_directory
            return self._json(200, choose_directory())
        if method == "POST" and path == "/api/finite-element/exports":
            body = self._body()
            body["kind"] = "finite_element"
            return self._json(201, self.server.create_job(body))
        if method == "GET" and path == "/api/finite-element/exports":
            folders = sorted((self.server.runtime / "jobs").iterdir(),
                             key=lambda item: item.stat().st_mtime, reverse=True)
            values = []
            for item in folders:
                if item.is_dir() and (item / "status.json").is_file() and len(item.name) == 16:
                    state = self.server.get_job(item.name)
                    if state.get("kind") == "finite_element":
                        values.append(state)
            return self._json(200, values[:100])
        if len(parts) == 5 and parts[:3] == ["api", "finite-element", "exports"] and parts[4] == "stop" and method == "POST":
            return self._json(200, self.server.stop(parts[3]))
        if len(parts) == 4 and parts[:3] == ["api", "finite-element", "exports"] and method == "GET":
            return self._json(200, self.server.get_job(parts[3]))
        if method == "POST" and path == "/api/uploads":
            return self._json(201, self.server.upload(query.get("name", [""])[0], self.rfile,
                                                    int(self.headers.get("Content-Length", "0"))))
        if len(parts) == 4 and parts[:2] == ["api", "uploads"] and parts[3] == "inspect" and method == "GET":
            if query.get('kind', ['target'])[0] == 'apdl_npz':
                from .apdl_npz import inspect_uploaded_npz
                return self._json(200, inspect_uploaded_npz(self.server, parts[2]))
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
        if method == "GET" and path == "/api/batches":
            folders = sorted((self.server.runtime / "batches").iterdir(),
                             key=lambda item: item.stat().st_mtime, reverse=True)
            statuses = []
            for folder in folders[:100]:
                if not folder.is_dir() or len(folder.name) != 16 or any(
                        char not in "0123456789abcdef" for char in folder.name):
                    continue
                status = json_record(folder / "status.json")
                if status:
                    statuses.append(status)
            return self._json(200, statuses)
        if len(parts) == 3 and parts[:2] == ["api", "batches"] and method == "GET":
            self.server.validate_id(parts[2])
            value = json_record(self.server.runtime / "batches" / parts[2] / "status.json")
            if value is None:
                raise FileNotFoundError("批次不存在")
            value["jobs"] = [self.server.get_job(job_id) for job_id in value["job_ids"]]
            return self._json(200, value)
        if len(parts) == 4 and parts[:2] == ["api", "batches"] and method == "POST":
            if parts[3] == "stop":
                from .batch_service import stop_batch
                return self._json(200, stop_batch(self.server, parts[2]))
            if parts[3] == "retry-failed":
                from .batch_service import retry_failed_batch
                return self._json(200, retry_failed_batch(self.server, parts[2]))
        if len(parts) == 4 and parts[:2] == ["api", "batches"] and parts[3] == "download" and method == "GET":
            from .batch_service import write_batch_archive
            with tempfile.TemporaryFile() as archive:
                write_batch_archive(self.server, parts[2], archive)
                length = archive.tell()
                archive.seek(0)
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(length))
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" +
                                 urllib.parse.quote(f"corrosion-batch-{parts[2]}.zip"))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                shutil.copyfileobj(archive, self.wfile, 1024 * 1024)
            return
        if len(parts) >= 3 and parts[:2] == ["api", "jobs"]:
            job_id = self.server.validate_id(parts[2])
            folder = self.server.runtime / "jobs" / job_id
            if len(parts) == 3 and method == "GET":
                return self._json(200, self.server.get_job(job_id))
            if len(parts) == 4 and method == "POST":
                if parts[3] in {'hide', 'unhide'}:
                    return self._json(200, self.server.set_job_hidden(job_id, parts[3] == 'hide'))
                if parts[3] == 'delete':
                    return self._json(200, self.server.delete_job(job_id, self._body().get('confirm_job_id')))
                if parts[3] == 'io':
                    from .task_io import configure_job
                    return self._json(200, configure_job(self.server, job_id, self._body()))
                if parts[3] == 'export':
                    from .task_io import export_job
                    from .job_history import history_guard
                    with history_guard(self.server):
                        return self._json(200, export_job(self.server, job_id))
                operation = {"resume": self.server.resume, "stop": self.server.stop,
                             "transfer": self.server.transfer}.get(parts[3])
                if operation:
                    return self._json(200, operation(job_id))
            if len(parts) == 4 and parts[3] == "spec" and method == "GET":
                return self._json(200, self.server.get_job(job_id)["spec"])
            if len(parts) == 4 and parts[3] == "log" and method == "GET":
                return self._json(200, {"text": self.server.log_tail(job_id)})
            if len(parts) >= 5 and parts[3] in {"download", "view"} and method == "GET":
                state = self.server.get_job(job_id)
                if len(parts) == 5 and parts[4] == "benchmark_bundle.zip" and state.get("kind") == "benchmark":
                    from .benchmark_archive import ensure_benchmark_bundle
                    bundle = ensure_benchmark_bundle(folder)
                    return self._file(bundle, download=True, download_name="benchmark_bundle.zip")
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
    return JobServer(host, port, runtime or DEFAULT_RUNTIME)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8523)
    args = parser.parse_args()
    server = make_server(port=args.port)
    print(f"腐蚀研究网站：http://127.0.0.1:{server.server_port}/", flush=True)
    server.serve_forever()

import copy
import importlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.config import default_simulation_config


def request(modes=None):
    return {"config": default_simulation_config(), "targets": [[100, 20, 2, 4, .6, .3]],
            "options": {"grid_w": 5, "grid_l": 6, "grid_n": 4, "steps": 3,
                        "population": 2, "workers": 2, "repeats": 2, "seed": 8,
                        "timeout_seconds": 120, "target_index": 0,
                        "modes": modes or ["numpy_serial", "numpy_parallel"]}}


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("backend.benchmark"),
                             "尚未实现性能对比模块")
        self.module = importlib.import_module("backend.benchmark")

    def test_freezes_inputs_without_changing_source_config(self):
        value = request(["taichi_gpu", "numpy_parallel"])
        original = copy.deepcopy(value)
        spec = self.module.prepare_benchmark(value)
        self.assertEqual(value, original)
        self.assertEqual(spec["options"]["modes"][0], "numpy_serial")
        self.assertEqual(spec["target"], value["targets"][0])
        self.assertEqual(len(spec["population"]), 2)
        self.assertEqual(spec["input_hash"], self.module.prepare_benchmark(value)["input_hash"])
        value["options"]["seed"] += 1
        self.assertNotEqual(spec["input_hash"], self.module.prepare_benchmark(value)["input_hash"])

    def test_rejects_invalid_modes_integers_and_resource_overflow(self):
        for patch in ({"modes": ["fake"]}, {"workers": True}, {"repeats": 0},
                      {"target_index": 2}, {"grid_w": 1000, "grid_l": 1000,
                                            "grid_n": 100, "population": 500}):
            value = request()
            value["options"].update(patch)
            with self.assertRaises(ValueError):
                self.module.prepare_benchmark(value)

    def test_gpu_fallback_is_never_reported_as_gpu(self):
        with self.assertRaisesRegex(ValueError, "CPU"):
            self.module.verify_arch("gpu", "x64")
        self.module.verify_arch("gpu", "cuda")
        self.module.verify_arch("cpu", "x64")

    def test_unavailable_backend_retains_dependency_failure_reason(self):
        import builtins
        from unittest.mock import patch
        from backend.benchmark_trial import BackendUnavailable, initialize_backend
        original_import = builtins.__import__
        def load(name, *args, **kwargs):
            if name == "taichi":
                raise ImportError("missing runtime.dll")
            return original_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=load):
            with self.assertRaisesRegex(BackendUnavailable, "runtime.dll"):
                initialize_backend("gpu")

    def test_difference_reports_all_state_arrays_and_shape_failures(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            arrays = {"objv": np.ones((2, 6)), "a": np.ones((2, 3, 4)),
                      "d": np.zeros((2, 3, 4)), "cl": np.zeros((2, 3))}
            np.savez(root / "a.npz", **arrays)
            np.savez(root / "b.npz", **arrays)
            result = self.module.compare_arrays(root / "a.npz", root / "b.npz")
            self.assertTrue(result["exact"])
            arrays["d"][0, 0, 0] = 2
            np.savez(root / "b.npz", **arrays)
            result = self.module.compare_arrays(root / "a.npz", root / "b.npz")
            self.assertFalse(result["exact"])
            self.assertEqual(result["arrays"]["d"]["max_abs_diff"], 2)
            arrays["a"] = np.ones((4, 5))
            np.savez(root / "b.npz", **arrays)
            self.assertFalse(self.module.compare_arrays(root / "a.npz", root / "b.npz")["exact"])

    def test_true_numpy_trial_repeats_same_results(self):
        from backend.benchmark_trial import run_trial
        spec = self.module.prepare_benchmark(request(["numpy_serial"]))
        with tempfile.TemporaryDirectory() as folder:
            result = run_trial(spec, "numpy_serial", Path(folder))
            self.assertEqual(result["state"], "completed")
            self.assertEqual(len(result["samples_seconds"]), 2)
            self.assertTrue(result["repeat_exact"])
            self.assertGreater(result["first_seconds"], 0)

    def test_real_isolated_serial_and_parallel_match_and_export(self):
        from backend.benchmark_service import run_benchmark
        spec = self.module.prepare_benchmark(request())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = run_benchmark(spec, root)
            self.assertEqual([r["state"] for r in result["rows"]], ["completed", "completed"])
            self.assertTrue(result["rows"][1]["comparison"]["exact"])
            self.assertEqual(result["rows"][0]["speedup"], 1.0)
            self.assertTrue((root / "outputs" / "benchmark_results.csv").is_file())
            self.assertTrue((root / "outputs" / "benchmark_bundle.zip").is_file())
            saved = json.loads((root / "outputs" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["input_hash"], spec["input_hash"])

    def test_api_creates_benchmark_job_and_rejects_invalid_before_launch(self):
        from unittest.mock import patch
        from backend.server import make_server
        with tempfile.TemporaryDirectory() as folder:
            server = make_server("127.0.0.1", 0, Path(folder))
            try:
                value = request()
                value["kind"] = "benchmark"
                state = server.create_job(value, launch=False)
                self.assertEqual(state["kind"], "benchmark")
                frozen = server.get_job(state["id"])["spec"]
                self.assertEqual(frozen["input_hash"], self.module.prepare_benchmark(value)["input_hash"])
                value["options"]["repeats"] = 0
                with patch.object(server, "launch") as launch:
                    with self.assertRaises(ValueError):
                        server.create_job(value)
                    launch.assert_not_called()
            finally:
                server.server_close()

    def test_service_restart_reserves_two_slots_for_inherited_benchmark(self):
        from backend.runner import _atomic_json
        from backend.job_service import JobService
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            job = root / "jobs" / ("c" * 16)
            job.mkdir(parents=True)
            _atomic_json(job / "status.json", {"kind": "benchmark", "state": "running", "pid": 1234})
            (job / "worker.lock").write_text("1234", encoding="ascii")
            service = JobService()
            with patch("backend.job_service.process_alive", return_value=True), patch("threading.Thread.start"):
                service.initialize(root)
                self.assertFalse(service.compute_slots.acquire(blocking=False))

    def test_real_service_launch_completes_benchmark(self):
        import time
        from backend.job_service import JobService
        service = JobService()
        with tempfile.TemporaryDirectory() as folder:
            service.initialize(Path(folder))
            value = request(["numpy_serial"])
            value["kind"] = "benchmark"
            state = service.create_job(value)
            deadline = time.monotonic() + 120
            while state["state"] in {"queued", "running"} and time.monotonic() < deadline:
                time.sleep(.1)
                state = service.get_job(state["id"])
            self.assertEqual(state["state"], "completed", state.get("error"))
            self.assertEqual(state["summary"]["rows"][0]["state"], "completed")

    def test_partial_report_has_downloadable_zip_before_final_mode(self):
        import zipfile
        from unittest.mock import patch
        from backend.benchmark_service import run_benchmark
        spec = self.module.prepare_benchmark(request())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch("backend.benchmark_service.runtime_provenance", return_value={}), patch("backend.benchmark_service.subprocess.Popen", side_effect=RuntimeError("模拟关闭")):
                with self.assertRaises(RuntimeError):
                    run_benchmark(spec, root)
            with zipfile.ZipFile(root / "outputs" / "benchmark_bundle.zip") as archive:
                self.assertIn("summary.json", archive.namelist())
                self.assertIn("benchmark_inputs.json", archive.namelist())

    def test_failed_baseline_keeps_other_results_without_speedup(self):
        from unittest.mock import patch
        from backend.benchmark_service import run_benchmark
        from backend.runner import _atomic_json
        class Finished:
            returncode = 0
            pid = 0
            def poll(self):
                return 0
        def launch(command, **kwargs):
            mode, destination = command[-2:]
            _atomic_json(Path(destination) / "trial.json",
                         {"mode": mode, "state": "failed" if mode == "numpy_serial" else "completed",
                          "median_seconds": 1.0, "samples_seconds": [1.0]})
            return Finished()
        spec = self.module.prepare_benchmark(request())
        with tempfile.TemporaryDirectory() as folder:
            with patch("backend.benchmark_service.runtime_provenance", return_value={}), patch("backend.benchmark_service.subprocess.Popen", side_effect=launch):
                report = run_benchmark(spec, Path(folder))
            self.assertEqual(report["rows"][1]["state"], "completed")
            self.assertNotIn("speedup", report["rows"][1])
            self.assertIn("基准失败", report["warning"])

    def test_terminate_trial_also_terminates_its_child(self):
        import subprocess
        import sys
        import psutil
        import time
        from backend.benchmark_service import terminate_tree
        script = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); print(p.pid,flush=True); time.sleep(60)"
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE,
                                   text=True, creationflags=flags)
        try:
            child_pid = int(process.stdout.readline())
            terminate_tree(process)
            time.sleep(.1)
            self.assertIsNotNone(process.poll())
            self.assertFalse(psutil.pid_exists(child_pid))
        finally:
            if process.poll() is None:
                terminate_tree(process)
            process.stdout.close()

    def test_download_length_matches_the_open_snapshot_during_report_replace(self):
        import io
        from backend.server import Handler
        class ReplacedPath:
            name = "report.zip"
            def is_file(self):
                return True
            def stat(self):
                return self.current.stat()
            def open(self, *args):
                return self.current.open(*args)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old, new = root / "old", root / "new"
            old.write_bytes(b"old")
            new.write_bytes(b"replacement is longer")
            path = ReplacedPath()
            path.current = old
            handler = object.__new__(Handler)
            handler.wfile = io.BytesIO()
            headers = {}
            handler.send_response = lambda status: None
            def send_header(key, value):
                headers[key] = value
                if key == "Content-Length":
                    path.current = new
            handler.send_header = send_header
            handler.end_headers = lambda: None
            handler._file(path)
            self.assertEqual(int(headers["Content-Length"]), len(handler.wfile.getvalue()))
            self.assertEqual(handler.wfile.getvalue(), b"old")


if __name__ == "__main__":
    unittest.main()

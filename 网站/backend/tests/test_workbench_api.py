import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.config import default_simulation_config
from backend.runner import _atomic_json
from backend.server import make_server


class WorkbenchAPITests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.server = make_server("127.0.0.1", 0, Path(self.folder.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.folder.cleanup()

    def request(self, path, value=None, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        request = Request(self.base + path, data=None if value is None else json.dumps(value).encode(),
                          headers=headers, method="GET" if value is None else "POST")
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def fake_job(self, job_id="a" * 16, kind="simulation", state="completed"):
        root = self.server.runtime / "jobs" / job_id
        root.mkdir()
        (root / "outputs").mkdir()
        _atomic_json(root / "status.json", {"id": job_id, "kind": kind, "state": state,
                                          "created_at": 1, "updated_at": 1, "pid": None})
        _atomic_json(root / "spec.json", {"kind": kind, "config": default_simulation_config(),
                                        "targets": [[10, 2, 1, 3, .2, .3]], "run_mode": "single"})
        return root

    def test_defaults_include_complete_catalog_and_resources(self):
        code, value = self.request("/api/defaults")
        self.assertEqual(code, 200)
        self.assertGreater(len(value["simulation_catalog"]), 75)
        self.assertIn("version", value)
        code, value = self.request("/api/config/validate", {
            "config": default_simulation_config(), "run_mode": "staged"})
        self.assertEqual(code, 200)
        self.assertIn("resources", value)

    def test_job_contains_frozen_configuration_and_result_summary(self):
        root = self.fake_job()
        _atomic_json(root / "outputs/summary.json", {"seed": 17, "stages": []})
        _atomic_json(root / "outputs/effective_config.json", {"actual_backend": "NumPy"})
        code, value = self.request("/api/jobs/" + "a" * 16)
        self.assertEqual(code, 200)
        self.assertIn("spec", value)
        self.assertEqual(value["summary"]["seed"], 17)
        self.assertEqual(value["effective_config"]["actual_backend"], "NumPy")

    def test_invalid_job_identifier_cannot_access_spec_or_outputs(self):
        code, _ = self.request("/api/jobs/not-a-valid-id/spec")
        self.assertEqual(code, 404)

    def test_cross_origin_write_is_rejected(self):
        with patch.object(self.server, "create_job") as create:
            code, _ = self.request("/api/jobs", {"kind": "simulation"}, origin="https://example.org")
        self.assertEqual(code, 403)
        create.assert_not_called()

    def test_closed_input_upload_is_not_retained(self):
        with self.assertRaises(ValueError):
            self.server.upload("scan.xyz", io.BytesIO(b"1 2"), 100)
        self.assertEqual(list((self.server.runtime / "uploads").iterdir()), [])

    def test_invalid_target_source_is_rejected_before_launch(self):
        config = default_simulation_config()
        with patch.object(self.server, "launch") as launch:
            code, value = self.request("/api/jobs", {
                "kind": "simulation", "config": config, "run_mode": "single",
                "targets": [[1, 2, 3, 4, .5, .6], [2, 3, 4, 5, .5, .6]]})
        self.assertEqual(code, 400)
        self.assertIn("一行", value["error"])
        launch.assert_not_called()

    def test_pointcloud_transfer_rejects_uncalibrated_result(self):
        root = self.fake_job(kind="pointcloud")
        _atomic_json(root / "outputs/summary.json", {
            "six_metrics": [1, 2, 3, 4, .5, .6], "calibration_ready": False,
            "calibration_issues": ["参考基准未确认"]})
        code, value = self.request("/api/jobs/" + "a" * 16 + "/transfer", {})
        self.assertEqual(code, 400)
        self.assertIn("参考", value["error"])

    def test_pointcloud_transfer_returns_actual_mat_targets(self):
        import numpy as np
        from scipy.io import savemat
        root = self.fake_job(kind="pointcloud")
        rows = [[10, 2, 1, 3, .2, .3]]
        _atomic_json(root / "outputs/summary.json", {
            "six_metrics": rows[0], "calibration_ready": True})
        savemat(root / "outputs/matlab_target.mat", {
            "target_data": np.asarray(rows), "calibration_ready": True})
        code, value = self.request("/api/jobs/" + "a" * 16 + "/transfer", {})
        self.assertEqual(code, 200)
        self.assertEqual(value["preview"]["targets"], rows)
        self.assertTrue(self.server.get_upload(value["upload"]["id"])[1].is_file())

    def test_history_skips_incomplete_job_directories(self):
        (self.server.runtime / "jobs" / ("b" * 16)).mkdir()
        self.fake_job()
        code, value = self.request("/api/jobs")
        self.assertEqual(code, 200)
        self.assertEqual(len(value), 1)

    def test_resume_is_prechecked_and_live_orphan_is_not_relaunched(self):
        root = self.fake_job(state="running")
        import os
        _atomic_json(root / "status.json", {"id": "a" * 16, "kind": "simulation",
                                          "state": "running", "pid": os.getpid(),
                                          "created_at": 1, "updated_at": 1})
        with patch.object(self.server, "launch") as launch:
            code, _ = self.request("/api/jobs/" + "a" * 16 + "/resume", {})
        self.assertEqual(code, 400)
        launch.assert_not_called()
        self.assertEqual(self.server.get_job("a" * 16)["state"], "running")

    def test_resumed_queued_task_ignores_dead_previous_process(self):
        self.fake_job(state="queued")
        from unittest.mock import Mock
        previous = Mock()
        previous.poll.return_value = 1
        self.server.processes["a" * 16] = previous
        self.server.pending_jobs.add("a" * 16)
        self.assertEqual(self.server.get_job("a" * 16)["state"], "queued")

    def test_canceled_queued_task_is_not_started_after_slot_acquired(self):
        self.fake_job(state="interrupted")
        with patch("backend.job_service.subprocess.Popen") as popen:
            self.server._start_process("a" * 16)
        self.assertFalse(popen.called)

    def test_queue_cancel_invalidates_old_scheduler_reservation(self):
        self.fake_job(state="queued")
        self.server.pending_jobs.add("a" * 16)
        self.server._launching_jobs["a" * 16] = "old-token"
        self.server.stop("a" * 16)
        self.assertNotIn("a" * 16, self.server._launching_jobs)

    def test_old_queue_thread_cannot_start_new_reservation(self):
        self.fake_job(state="queued")
        with patch("backend.job_service.threading.Thread") as thread:
            self.server.launch("a" * 16)
        old_scheduled = thread.call_args.kwargs["target"]
        self.server._launching_jobs["a" * 16] = "new-reservation"
        with patch.object(self.server, "_start_process") as start:
            old_scheduled()
        start.assert_not_called()
        self.assertEqual(self.server._launching_jobs["a" * 16], "new-reservation")

    def test_service_restart_counts_live_locked_workers(self):
        for job_id, pid in (("a" * 16, 1234), ("b" * 16, 5678)):
            root = self.fake_job(job_id=job_id, state="running")
            state = json.loads((root / "status.json").read_text())
            state["pid"] = pid
            _atomic_json(root / "status.json", state)
            (root / "worker.lock").write_text(str(pid), encoding="ascii")
        with patch("backend.job_service.process_alive", return_value=True), \
                patch("backend.job_service.threading.Thread") as thread:
            restarted = make_server("127.0.0.1", 0, self.server.runtime)
        try:
            self.assertEqual(len(restarted.inherited_processes), 2)
            self.assertFalse(restarted.compute_slots.acquire(blocking=False))
            watcher = thread.call_args.kwargs["target"]
            with patch("backend.job_service.process_alive", return_value=False):
                watcher()
            self.assertTrue(restarted.compute_slots.acquire(blocking=False))
            self.assertTrue(restarted.compute_slots.acquire(blocking=False))
            self.assertFalse(restarted.compute_slots.acquire(blocking=False))
        finally:
            restarted.server_close()


if __name__ == "__main__":
    unittest.main()

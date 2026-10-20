import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np

from backend.runner import _atomic_json
from backend.server import make_server
from backend.worker import run_job


class FiniteElementApiTests(unittest.TestCase):
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

    def request(self, path, value=None):
        request = Request(self.base + path,
                          data=None if value is None else json.dumps(value).encode(),
                          headers={"Content-Type": "application/json"},
                          method="GET" if value is None else "POST")
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def fake_simulation(self, job_id="a" * 16, state="completed"):
        root = self.server.runtime / "jobs" / job_id
        (root / "outputs").mkdir(parents=True)
        _atomic_json(root / "status.json", {"id": job_id, "kind": "simulation", "state": state,
                                              "created_at": 1, "updated_at": 1, "pid": None})
        _atomic_json(root / "spec.json", {"kind": "simulation", "run_mode": "single", "config": {}})
        np.savez(root / "outputs" / "simulation.npz", perfect_a=np.ones((2, 3, 4), dtype=np.uint8))
        return root

    def test_create_export_job_freezes_source_and_options(self):
        root = self.fake_simulation()
        with patch.object(self.server, "launch") as launch:
            code, value = self.request("/api/finite-element/exports", {
                "source_job_id": "a" * 16,
                "source_kind": "simulation",
                "options": {"output_variable": "Z_filled", "space_z_um": 25,
                            "grid_spacing_mm": 0.05},
            })
        self.assertEqual(code, 201)
        self.assertEqual(value["kind"], "finite_element")
        launch.assert_called_once()
        spec = json.loads((self.server.runtime / "jobs" / value["id"] / "spec.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["source_job_id"], "a" * 16)
        self.assertEqual(spec["options"]["output_variable"], "Z_filled")
        self.assertTrue(Path(spec["source_path"]).is_file())
        detail_code, detail = self.request("/api/finite-element/exports/" + value["id"])
        self.assertEqual(detail_code, 200)
        self.assertEqual(detail["kind"], "finite_element")

    def test_export_rejects_incomplete_source_job(self):
        self.fake_simulation(state="running")
        code, value = self.request("/api/finite-element/exports", {
            "source_job_id": "a" * 16, "source_kind": "simulation", "options": {}})
        self.assertEqual(code, 400)
        self.assertIn("已完成", value["error"])

    def test_worker_generates_bundle_and_marks_task_completed(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime = Path(runtime_dir)
            job_id = "b" * 16
            root = runtime / "jobs" / job_id
            (root / "inputs").mkdir(parents=True)
            (root / "outputs").mkdir()
            np.savez(root / "inputs" / "source.npz",
                     perfect_a=np.ones((2, 3, 4), dtype=np.uint8))
            _atomic_json(root / "spec.json", {
                "kind": "finite_element", "source_kind": "simulation",
                "frozen_source_path": "inputs/source.npz",
                "options": {"output_variable": "Z_filled", "space_z_um": 25.0,
                            "grid_spacing_mm": 0.05, "origin_x_mm": 0.0,
                            "origin_y_mm": 0.0, "precision": "%.6f"},
            })
            _atomic_json(root / "status.json", {"id": job_id, "kind": "finite_element",
                                                  "state": "queued", "created_at": 1,
                                                  "updated_at": 1})
            run_job(job_id, runtime)
            status = json.loads((root / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "completed")
            self.assertTrue((root / "outputs" / "Z_filled.mat").is_file())
            self.assertTrue((root / "outputs" / "finite_element_input_bundle.zip").is_file())


if __name__ == "__main__":
    unittest.main()

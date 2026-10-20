import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import savemat

from backend.system_info import sha256
from backend.visualization_service import inspect_upload, inspect_simulation_stage, simulation_sources


class UploadService:
    def __init__(self, path):
        self.path = path
        self.record = {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}

    def get_upload(self, upload_id):
        if upload_id != "a" * 32:
            raise FileNotFoundError("upload missing")
        return self.record, self.path


class SimulationService:
    def __init__(self, runtime, job_id):
        self.runtime = runtime
        self.job_id = job_id

    def validate_id(self, value):
        if value != self.job_id:
            raise FileNotFoundError("job missing")
        return value

    def get_job(self, value):
        return {"id": value, "kind": "simulation", "state": "completed", "case_name": "test",
                "spec": {"config": {"GEOMETRY_CONFIG": {"space_z_um": 10}}}}


class VisualizationServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_npz_stage_and_matrix_metadata(self):
        path = self.root / "stages.npz"
        source = np.arange(2 * 4 * 5 * 3, dtype=np.uint8).reshape(2, 4, 5, 3)
        np.savez(path, perfect_a=source)
        result = inspect_upload(UploadService(path), {"upload_id": "a" * 32, "stage": 2})
        self.assertEqual(result["source_shape"], [2, 4, 5, 3])
        self.assertEqual(result["preview_shape"], [4, 5])
        self.assertEqual(result["stage"], 2)
        self.assertEqual(result["stage_count"], 2)
        self.assertEqual(result["mode"], "matrix")

    def test_csv_numeric_grid_and_header(self):
        path = self.root / "grid.csv"
        path.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
        result = inspect_upload(UploadService(path), {"upload_id": "a" * 32})
        self.assertEqual(result["source_shape"], [2, 2])
        self.assertTrue(result["header_detected"])
        self.assertEqual(result["minimum"], 1)
        self.assertEqual(result["maximum"], 4)

    def test_mat_selects_numeric_matrix_without_rewriting_source(self):
        path = self.root / "surface.mat"
        savemat(path, {"Z_filled": np.array([[0.0, 1.0], [2.0, 3.0]]), "metadata": np.array([[7]])})
        original_hash = sha256(path)
        result = inspect_upload(UploadService(path), {"upload_id": "a" * 32})
        self.assertEqual(result["variable"], "Z_filled")
        self.assertEqual(result["source_shape"], [2, 2])
        self.assertEqual(sha256(path), original_hash)

    def test_xyz_returns_scatter_sample(self):
        path = self.root / "surface.xyz"
        path.write_text("0 0 1\n1 0 2\n0 1 3\n", encoding="utf-8")
        result = inspect_upload(UploadService(path), {"upload_id": "a" * 32})
        self.assertEqual(result["mode"], "scatter")
        self.assertEqual(result["source_shape"], [3, 3])
        self.assertEqual(len(result["preview"]), 3)

    def test_saved_simulation_stages_use_original_surface_conversion(self):
        job_id = "b" * 16
        output = self.root / "jobs" / job_id / "outputs"
        output.mkdir(parents=True)
        state = np.ones((2, 3, 4, 5), dtype=np.uint8)
        state[0, :, :, 0] = 0
        state[1, :, :, :2] = 0
        np.savez(output / "simulation.npz", a_sd=state)
        service = SimulationService(self.root, job_id)
        self.assertEqual(simulation_sources(service)["jobs"][0]["stage_count"], 2)
        result = inspect_simulation_stage(service, {"job_id": job_id, "stage": 2})
        self.assertEqual(result["shape"], [3, 4])
        self.assertEqual(result["maximum_mm"], 0.02)
        self.assertEqual(result["max_position_preview_index"], [0, 0])
        self.assertEqual(result["rule"].startswith("复用 export_apdl_mat.surface_from_ca_state"), True)


if __name__ == "__main__":
    unittest.main()

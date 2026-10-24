import io
import json
import tempfile
import threading
import time
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from backend.batch_service import batch_archive_bytes, retry_failed_batch, stop_batch
from backend.config import default_simulation_config
from backend.pointcloud_runner import inspect_xyz, run_pointcloud
from backend.server import make_server
from backend.git_sync import _git


class PointCloudDiagnosticsTests(unittest.TestCase):
    def test_inspect_xyz_reports_duplicates_and_axis_health(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "scan.xyz"
            source.write_text("0 0 1\n0 0 1\n5 0 2\n0 7 3\n", encoding="utf-8")
            result = inspect_xyz(source)
            self.assertEqual(result["diagnostics"]["duplicate_points"], 1)
            self.assertEqual(result["diagnostics"]["nonzero_axes"], [True, True, True])
            self.assertEqual(result["diagnostics"]["finite_points"], 4)

    def test_pointcloud_writes_timing_breakdown(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "scan.xyz"
            source.write_text("0 0 1\n5 0 2\n0 7 3\n", encoding="utf-8")
            matlab = root / "matlab.exe"
            matlab.write_bytes(b"stub")
            job = root / "job"
            target = job / "outputs" / "pointcloud" / "matlab_target.mat"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"mat")
            (job / "outputs" / "matlab_timing.json").write_text(json.dumps({
                "input_seconds": .1, "preprocess_seconds": .2,
                "analysis_seconds": .3, "numeric_export_seconds": .4,
                "plot_export_seconds": .5, "target_export_seconds": .6,
                "total_seconds": 2.1,
            }), encoding="utf-8")
            with patch("backend.pointcloud_runner.subprocess.run") as run:
                run.return_value.returncode = 0
                with patch("backend.pointcloud_runner.loadmat", return_value={
                    "target_data": [1, 2, 3, 4, 5, 6],
                    "height_smoothed_mm": np.arange(6., dtype=float).reshape(2, 3),
                    "spacing_um": 500.,
                    "calibration_ready": True,
                    "calibration_issues": [],
                }):
                    result = run_pointcloud(job, source, source, {}, matlab_bin=matlab)
            timing = json.loads((job / "outputs" / "timing.json").read_text(encoding="utf-8"))
            self.assertIn("matlab_seconds", timing)
            self.assertIn("postprocess_seconds", timing)
            self.assertGreaterEqual(timing["total_seconds"], timing["matlab_seconds"])
            self.assertEqual(result["timing"]["matlab_seconds"], timing["matlab_seconds"])
            self.assertEqual(timing["matlab_preprocess_seconds"], .2)
            self.assertEqual(timing["matlab_plot_export_seconds"], .5)
            self.assertTrue((job / "outputs" / "pointcloud" / "measured_surface_smoothed.mat").is_file())
            self.assertTrue((job / "outputs" / "pointcloud" / "measured_surface_smoothed.json").is_file())
            self.assertEqual(result["smoothed_surface"]["source_variable"], "height_smoothed_mm")
            self.assertEqual(result["smoothed_surface"]["dx_mm"], .5)
            self.assertEqual(result["smoothed_surface"]["size_x_mm"], 1.)
            from scipy.io import loadmat
            values = loadmat(job / "outputs" / "pointcloud" / "measured_surface_smoothed.mat")
            self.assertEqual([key for key in values if not key.startswith('__')],
                             ['Z_filled', 'height_matrix_mm', 'corrosion_depth_matrix_mm',
                              'x_coordinates_mm', 'y_coordinates_mm', 'processed_xyz_mm'])
            np.testing.assert_array_equal(values['Z_filled'], np.arange(6.).reshape(2, 3))
            np.testing.assert_array_equal(values['x_coordinates_mm'].ravel(), [0, .5, 1])
            self.assertEqual(values['processed_xyz_mm'].shape, (6, 3))

    def test_processed_pointcloud_region_preserves_coordinates_and_depth(self):
        from scipy.io import savemat, loadmat
        from backend.pointcloud_regions import export_region
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            output = job / 'outputs' / 'pointcloud'
            output.mkdir(parents=True)
            height = np.arange(20., dtype=float).reshape(4, 5)
            x, y = np.arange(5.), np.arange(4.)
            savemat(output / 'measured_surface_smoothed.mat', {
                'height_matrix_mm': height, 'corrosion_depth_matrix_mm': height.max() - height,
                'x_coordinates_mm': x, 'y_coordinates_mm': y,
            })
            result = export_region(job, 'X', 2, 2)
            self.assertEqual(result['actual_range_mm'], [1., 3.])
            self.assertTrue(result['corrosion_depth_available'])
            self.assertEqual(result['depth_source'], 'relative_to_full_surface_max')
            self.assertIn('not verified pristine-reference depth', result['depth_semantics'])
            values = loadmat(output / 'regions' / result['region_id'] / 'processed_region.mat')
            np.testing.assert_array_equal(values['x_coordinates_mm'].ravel(), [1, 2, 3])
            np.testing.assert_array_equal(values['height_matrix_mm'], height[:, 1:4])
            np.testing.assert_array_equal(values['corrosion_depth_matrix_mm'], (height.max() - height)[:, 1:4])

    def test_independent_generated_surface_can_be_cropped(self):
        from scipy.io import savemat, loadmat
        from backend.pointcloud_regions import export_region
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            output = job / 'outputs' / 'front'
            output.mkdir(parents=True)
            height = np.arange(20., dtype=float).reshape(4, 5)
            savemat(output / 'Z_filled.mat', {'Z_filled': height})
            (output / 'manifest.json').write_text(json.dumps({
                'output_variable': 'Z_filled', 'matrix_shape': [4, 5],
                'origin_x_mm': 0, 'origin_y_mm': 0, 'dx_mm': 1, 'dy_mm': 1,
                'value_mode': 'height',
            }), encoding='utf-8')
            result = export_region(job, 'X', 2, 2, 'surface_generation', 'front', 'raw')
            self.assertEqual(result['actual_range_mm'], [1., 3.])
            self.assertTrue(result['files'][0].startswith('front/regions/'))
            values = loadmat(job / 'outputs' / result['files'][0])
            np.testing.assert_array_equal(values['height_matrix_mm'], height[:, 1:4])
            self.assertFalse(result['corrosion_depth_available'])
            self.assertEqual(values['corrosion_depth_matrix_mm'].size, 0)
            self.assertEqual(values['depth_source'], 'not_calibrated')
            self.assertEqual(result['preview_depth_mm'], [])

    def test_independent_depth_input_is_preserved_without_recalculation(self):
        from scipy.io import savemat, loadmat
        from backend.pointcloud_regions import export_region
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            output = job / 'outputs' / 'front'
            output.mkdir(parents=True)
            depth = np.arange(20., dtype=float).reshape(4, 5) / 10
            savemat(output / 'a_sd.mat', {'a_sd': depth})
            (output / 'manifest.json').write_text(json.dumps({
                'output_variable': 'a_sd', 'matrix_shape': [4, 5],
                'origin_x_mm': 0, 'origin_y_mm': 0, 'dx_mm': 1, 'dy_mm': 1,
                'value_mode': 'depth',
            }), encoding='utf-8')
            result = export_region(job, 'X', 2, 2, 'surface_generation', 'front', 'raw')
            values = loadmat(job / 'outputs' / result['files'][0])
            self.assertTrue(result['corrosion_depth_available'])
            self.assertEqual(result['depth_source'], 'input_depth_matrix')
            np.testing.assert_array_equal(values['corrosion_depth_matrix_mm'], depth[:, 1:4])


class ExcelTargetTests(unittest.TestCase):
    def test_xlsx_header_and_rows_are_read_as_six_metrics(self):
        from openpyxl import Workbook
        from backend.targets import inspect_target, load_targets
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "metrics.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["mean", "nonuniform", "ratio", "depth", "ratio_sd", "depth_sd"])
            sheet.append([10, 2, 1, 3, .2, .3])
            sheet.append([12, 3, 1, 4, .3, .4])
            workbook.save(path)
            result = inspect_target(path)
            self.assertEqual(result["shape"], [2, 6])
            self.assertEqual(result["targets"], [[10, 2, 1, 3, .2, .3], [12, 3, 1, 4, .3, .4]])
            self.assertEqual(load_targets(path), result["targets"])


class GitPreviewTests(unittest.TestCase):
    def test_git_wrapper_preserves_short_status_prefix(self):
        with patch("backend.git_sync.shutil.which", return_value="git"), patch(
                "backend.git_sync.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = " M README.md\n?? new.txt\n"
            self.assertEqual(_git("status", "--short"), " M README.md\n?? new.txt")


class BatchOperationsTests(unittest.TestCase):
    def test_batch_http_list_stop_and_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            server = make_server("127.0.0.1", 0, Path(folder))
            job = server.create_job({"kind": "simulation", "run_mode": "single",
                "config": default_simulation_config(),
                "targets": [[10, 2, 1, 3, .2, .3]]}, launch=False)
            batch_id = "0123456789abcdef"
            status_path = Path(folder) / "batches" / batch_id / "status.json"
            status_path.parent.mkdir()
            status_path.write_text(json.dumps({"id": batch_id, "job_ids": [job["id"]],
                                               "state": "queued"}), encoding="utf-8")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}/api/batches"
            try:
                with urllib.request.urlopen(base) as response:
                    self.assertEqual(json.load(response)[0]["id"], batch_id)
                with urllib.request.urlopen(f"{base}/{batch_id}/download") as response:
                    with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                        self.assertTrue(any(name.endswith("spec.json") for name in archive.namelist()))
                request = urllib.request.Request(f"{base}/{batch_id}/stop", data=b"{}", method="POST")
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(json.load(response)["state"], "stopped")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_batch_archive_contains_status_and_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            server = make_server("127.0.0.1", 0, Path(folder))
            try:
                batch = Path(folder) / "batches" / "0123456789abcdef"
                batch.mkdir(parents=True)
                (batch / "status.json").write_text(json.dumps({
                    "id": "0123456789abcdef", "job_ids": ["fedcba9876543210"]
                }), encoding="utf-8")
                job = Path(folder) / "jobs" / "fedcba9876543210" / "outputs"
                job.mkdir(parents=True)
                (Path(folder) / "jobs" / "fedcba9876543210" / "status.json").write_text(
                    json.dumps({"id": "fedcba9876543210", "state": "completed"}), encoding="utf-8")
                (job / "summary.json").write_text("{}", encoding="utf-8")
                archive = batch_archive_bytes(server, "0123456789abcdef")
                with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
                    self.assertTrue(any(name.endswith("summary.json") for name in zipped.namelist()))
                    self.assertTrue(any(name.endswith("status.json") for name in zipped.namelist()))
            finally:
                server.server_close()

    def test_stop_batch_cancels_queued_case(self):
        with tempfile.TemporaryDirectory() as folder:
            server = make_server("127.0.0.1", 0, Path(folder))
            try:
                job = server.create_job({"kind": "simulation", "run_mode": "single",
                    "config": default_simulation_config(),
                    "targets": [[10, 2, 1, 3, .2, .3]]}, launch=False)
                batch_id = "0123456789abcdef"
                status = Path(folder) / "batches" / batch_id / "status.json"
                status.parent.mkdir()
                status.write_text(json.dumps({"id": batch_id, "job_ids": [job["id"]],
                                              "state": "queued"}), encoding="utf-8")
                result = stop_batch(server, batch_id)
                self.assertEqual(result["state"], "stopped")
                self.assertEqual(server.get_job(job["id"])["state"], "interrupted")
            finally:
                server.server_close()

    def test_retry_watcher_finishes_when_resumed_case_completes(self):
        with tempfile.TemporaryDirectory() as folder:
            server = make_server("127.0.0.1", 0, Path(folder))
            try:
                job = server.create_job({"kind": "simulation", "run_mode": "single",
                    "config": default_simulation_config(),
                    "targets": [[10, 2, 1, 3, .2, .3]]}, launch=False)
                job_status = Path(folder) / "jobs" / job["id"] / "status.json"
                job_status.write_text(json.dumps({**job, "state": "failed"}), encoding="utf-8")
                batch_id = "0123456789abcdef"
                batch_status = Path(folder) / "batches" / batch_id / "status.json"
                batch_status.parent.mkdir()
                batch_status.write_text(json.dumps({"id": batch_id, "job_ids": [job["id"]],
                                                    "state": "needs_attention"}), encoding="utf-8")
                def complete(_):
                    job_status.write_text(json.dumps({**job, "state": "completed"}), encoding="utf-8")
                with patch.object(server, "resume", side_effect=complete):
                    result = retry_failed_batch(server, batch_id)
                self.assertEqual(result["retried_job_ids"], [job["id"]])
                deadline = time.time() + 2
                from backend.system_info import json_record
                while time.time() < deadline:
                    if json_record(batch_status)["state"] == "completed":
                        break
                    time.sleep(.02)
                self.assertEqual(json_record(batch_status)["state"], "completed")
            finally:
                server.server_close()


if __name__ == "__main__":
    unittest.main()

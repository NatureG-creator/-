import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from backend.config import default_simulation_config
from backend.runner import precheck_resume, run_simulation


class RunnerTests(unittest.TestCase):
    def tiny_spec(self):
        config = default_simulation_config()
        config["GEOMETRY_CONFIG"].update(grid_w=5, grid_l=6, grid_n=4, space_xy_um=25, space_z_um=25)
        config["STAGE_GA_CONFIG"].update(F=3, nind=4, selected_count=2, maxgen=3, parallel_workers=1)
        config["SINGLE_STAGE_GA_CONFIG"].update(F=2, nind=2, selected_count=1, maxgen=2, parallel_workers=1)
        return {"kind": "simulation", "run_mode": "single", "config": config,
                "targets": [[10, 2, 1, 3, .2, .3]]}

    def test_numerical_outputs_survive_plot_failure_and_show_actual_metrics(self):
        spec = self.tiny_spec()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            def failed_plot(*args, **kwargs):
                self.assertTrue((path / "outputs" / "summary.json").is_file(),
                                "绘图前必须持久保存汇总数字")
                raise RuntimeError("plot intentionally unavailable")
            with patch("backend.runner._plot_stage", failed_plot):
                result = run_simulation(spec, path)
            summary = json.loads((path / "outputs" / "summary.json").read_text(encoding="utf-8"))
            self.assertIn("actual_metrics", summary["stages"][0])
            self.assertNotEqual(summary["stages"][0]["actual_metrics"]["mean_depth_um"], spec["targets"][0][0])
            self.assertTrue(summary["warnings"])
            self.assertTrue((path / "outputs" / "timing.json").is_file())
            self.assertTrue((path / "outputs" / "effective_config.json").is_file())
            csv = (path / "outputs" / "stage_metrics.csv").read_text(encoding="utf-8-sig")
            self.assertIn("target_mean_depth_um", csv)
            self.assertIn("actual_mean_depth_um", csv)

    def test_completed_stage_cannot_be_reused_with_changed_config(self):
        spec = self.tiny_spec()
        with tempfile.TemporaryDirectory() as folder:
            run_simulation(spec, Path(folder))
            spec["config"]["GA_CONFIG"]["seed"] += 1
            with self.assertRaisesRegex(ValueError, "配置"):
                run_simulation(spec, Path(folder))

    def test_first_stage_export_exists_before_next_stage_runs(self):
        spec = self.tiny_spec()
        spec["run_mode"] = "staged"
        spec["targets"].append([12, 3, 1, 4, .2, .3])
        from backend.runner import run_strict_stage
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            def checked_stage(target, config, stage_number, *args, **kwargs):
                if stage_number == 2:
                    self.assertTrue((path / "outputs" / "stage_metrics.csv").is_file())
                    summary = json.loads((path / "outputs" / "summary.json").read_text(encoding="utf-8"))
                    self.assertEqual(len(summary["stages"]), 1)
                    raise InterruptedError("stage boundary")
                return run_strict_stage(target, config, stage_number, *args, **kwargs)
            with patch("backend.runner.run_strict_stage", checked_stage):
                with self.assertRaises(InterruptedError):
                    run_simulation(spec, path)

    def test_convergence_is_exported_while_stage_is_still_running(self):
        spec = self.tiny_spec()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            def interrupt(event):
                if event["phase"] == "generation_completed":
                    csv_path = path / "outputs" / "stage_001_convergence.csv"
                    self.assertTrue(csv_path.is_file(), "每代收敛数据应立即导出")
                    raise InterruptedError("generation boundary")
            with self.assertRaises(InterruptedError):
                run_simulation(spec, path, progress=interrupt)

    def test_spawned_fast_workers_honor_adjusted_scientific_config(self):
        spec = self.tiny_spec()
        spec["config"]["mode"] = "fast"
        spec["config"]["CA_CONFIG"].update(initial_d=7.0, initial_cl=2.0)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_simulation(spec, root / "serial")
            spec["config"]["SINGLE_STAGE_GA_CONFIG"]["parallel_workers"] = 2
            run_simulation(spec, root / "parallel")
            with np.load(root / "serial" / "outputs" / "stage_001.npz") as serial:
                with np.load(root / "parallel" / "outputs" / "stage_001.npz") as parallel:
                    for key in ("perfect_result", "perfect_parameter", "perfect_a", "perfect_d", "perfect_cl"):
                        np.testing.assert_array_equal(serial[key], parallel[key])

    def test_configured_heatmap_dimensions_and_dpi_are_applied(self):
        from PIL import Image
        spec = self.tiny_spec()
        spec["config"]["FIGURE_CONFIG"].update(auto_heatmap_figsize=[4, 3], auto_plot_dpi=100)
        with tempfile.TemporaryDirectory() as folder:
            run_simulation(spec, Path(folder))
            with Image.open(Path(folder) / "outputs" / "stage_001.png") as image:
                self.assertEqual(image.size, (400, 300))

    def test_taichi_requested_worker_cannot_silently_fall_back(self):
        from backend.runner import _configured_worker_init
        from backend.strict_ga import scientific_settings
        config = self.tiny_spec()["config"]
        args = (np.array([10, 2, 1, 3, .2, .3]), 10, 2, 4, 5, 6, 25, 1,
                None, None, None, True, "cpu")
        with scientific_settings(config):
            with patch("backend.runner._engine_worker_init"):
                with patch("corrosion_model.taichi_accel_优化版.taichi_available", return_value=False):
                    with self.assertRaisesRegex(RuntimeError, "Taichi"):
                        _configured_worker_init(config, *args)

    def test_two_stage_job_resume_and_read_only_precheck(self):
        from backend.checkpoint import sha256_file
        spec = self.tiny_spec()
        spec["run_mode"] = "staged"
        spec["targets"].append([12, 3, 1, 4, .2, .3])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_simulation(spec, root / "continuous")
            def interrupt(event):
                if (event.get("stage") == 2 and event.get("phase") == "checkpoint" and
                        event.get("completed_individuals") == 1):
                    raise InterruptedError("second stage individual committed")
            with self.assertRaises(InterruptedError):
                run_simulation(spec, root / "resume", progress=interrupt)
            before = {str(path): sha256_file(path) for path in (root / "resume").rglob("*") if path.is_file()}
            checked = precheck_resume(spec, root / "resume")
            self.assertTrue(checked["available"])
            self.assertTrue(checked["stages"][0]["stage_exported"])
            self.assertEqual(checked["stages"][1]["completed_individuals"], 1)
            after = {str(path): sha256_file(path) for path in (root / "resume").rglob("*") if path.is_file()}
            self.assertEqual(before, after, "恢复预检必须只读")
            run_simulation(spec, root / "resume")
            with np.load(root / "continuous" / "outputs" / "simulation.npz") as continuous:
                with np.load(root / "resume" / "outputs" / "simulation.npz") as resumed:
                    for key in continuous.files:
                        np.testing.assert_array_equal(continuous[key], resumed[key])

    def test_two_stage_result_and_export(self):
        config = default_simulation_config()
        config["GEOMETRY_CONFIG"].update(grid_w=5, grid_l=6, grid_n=4, space_xy_um=25, space_z_um=25)
        config["STAGE_GA_CONFIG"].update(F=3, nind=4, selected_count=2, maxgen=3, parallel_workers=1)
        targets = [[10, 2, 1, 3, 0.2, 0.3], [12, 3, 1, 4, 0.2, 0.3]]
        spec = {"kind": "simulation", "run_mode": "staged", "config": config, "targets": targets}
        with tempfile.TemporaryDirectory() as folder:
            job_dir = Path(folder)
            result = run_simulation(spec, job_dir)
            self.assertEqual(result["stages_completed"], 2)
            with np.load(job_dir / "outputs" / "simulation.npz", allow_pickle=False) as data:
                self.assertEqual(data["perfect_result_sd"].shape, (2, 4))
                self.assertEqual(data["a_sd"].shape[0], 2)
            self.assertEqual(len(json.loads((job_dir / "outputs" / "summary.json").read_text(encoding="utf-8"))["stages"]), 2)


if __name__ == "__main__":
    unittest.main()

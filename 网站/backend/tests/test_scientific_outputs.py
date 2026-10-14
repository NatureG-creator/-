import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from backend.config import default_simulation_config


class ScientificOutputTests(unittest.TestCase):
    def test_absent_pit_population_is_null_instead_of_invented_zero(self):
        from backend import runner
        self.assertTrue(hasattr(runner, "actual_surface_metrics"), "需要真实形貌指标导出")
        config = default_simulation_config()
        a = np.ones((5, 6, 4))
        metrics, notes = runner.actual_surface_metrics(a, config)
        self.assertEqual(metrics["mean_depth_um"], 0)
        self.assertIsNone(metrics["mu_log_ratio"])
        self.assertIsNone(metrics["sigma_log_depth"])
        self.assertIn("mu_log_ratio", notes)

    def test_streamed_compatibility_export_matches_shapes_without_stack(self):
        from backend import runner
        self.assertTrue(hasattr(runner, "export_compatibility_npz"), "需要逐阶段流式合并")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = []
            for index in range(2):
                path = root / f"stage_{index}.npz"
                np.savez(path, perfect_result=np.arange(4) + index,
                         perfect_parameter=np.arange(10) + index,
                         perfect_a=np.full((3, 4, 2), index, dtype=float),
                         perfect_d=np.full((3, 4, 2), index + 10, dtype=float),
                         perfect_cl=np.full((3, 4), index + 20, dtype=float))
                paths.append(path)
            with patch("numpy.stack", side_effect=AssertionError("不得全阶段驻内存")):
                runner.export_compatibility_npz(root / "simulation.npz", paths)
            with np.load(root / "simulation.npz", allow_pickle=False) as result:
                self.assertEqual(result["a_sd"].shape, (2, 3, 4, 2))
                np.testing.assert_array_equal(result["a_sd"][1], 1)
                np.testing.assert_array_equal(result["perfect_cl"], 21)
                np.testing.assert_array_equal(result["stage_numbers"], [1, 2])

    def test_defined_actual_metrics_match_original_ca_postprocess(self):
        from backend.runner import actual_surface_metrics, METRIC_NAMES
        from backend.strict_ga import scientific_settings
        from corrosion_model.ca_优化版 import run_ca
        config = default_simulation_config()
        config["GEOMETRY_CONFIG"].update(grid_w=31, grid_l=31, grid_n=8, space_z_um=25)
        config["POSTPROCESS_CONFIG"].update(gaussian_sigma=.1, auto_plot_window_size=1)
        config["MATLAB_CA_COMPARISON_CONFIG"].update(min_prominence=.01, min_distance=3)
        a = np.ones((31, 31, 8))
        for x, y, depth in ((4, 4, 1), (4, 23, 3), (23, 4, 4), (23, 23, 2)):
            a[x:x + 3, y:y + 3, :depth] = 0
        xy = np.array([0, 0, 0, 5, 1, 0, 1, 0, 0, 1], dtype=float)
        with scientific_settings(config):
            original = run_ca(xy, 1, a, np.ones(6), 1000, 8, 31, 31, 25,
                              np.full(a.shape, 3.0), 2, np.zeros((31, 31)),
                              np.random.default_rng(17), use_taichi=False)
        metrics, notes = actual_surface_metrics(original.a, config)
        self.assertEqual(notes, {})
        np.testing.assert_allclose([metrics[name] for name in METRIC_NAMES], original.cs + 1,
                                   rtol=1e-12, atol=1e-12)


if __name__ == "__main__":
    unittest.main()

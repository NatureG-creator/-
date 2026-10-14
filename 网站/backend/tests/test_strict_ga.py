import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.config import default_simulation_config
from backend.strict_ga import run_strict_stage
from corrosion_model.ga_优化版 import GAConfig, run_ga


class StrictResumeTests(unittest.TestCase):
    def test_mid_generation_resume_matches_uninterrupted(self):
        config = default_simulation_config()
        config["GEOMETRY_CONFIG"].update(grid_w=5, grid_l=6, grid_n=4, space_xy_um=25, space_z_um=25)
        config["STAGE_GA_CONFIG"].update(F=3, nind=4, selected_count=2, maxgen=4, parallel_workers=1)
        target = np.array([10.0, 2.0, 1.0, 3.0, 0.2, 0.3])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            continuous = run_strict_stage(target, config, 1, root / "continuous", "same")

            def interrupt(event):
                if event["generation"] == 1 and event["completed_individuals"] == 1:
                    raise InterruptedError("synthetic stop")

            with self.assertRaises(InterruptedError):
                run_strict_stage(target, config, 1, root / "resumed", "same", progress=interrupt)
            resumed = run_strict_stage(target, config, 1, root / "resumed", "same")
            for key in ("perfect_result", "perfect_parameter", "perfect_a", "perfect_d", "perfect_cl"):
                np.testing.assert_array_equal(getattr(continuous, key), getattr(resumed, key))
            options = config["STAGE_GA_CONFIG"]
            reference = run_ga(
                5, 6, 4, float(target[0]), target, None, 3, 1, 25.0,
                None, None, seed=config["GA_CONFIG"]["seed"],
                config=GAConfig(nind=options["nind"], selected_count=options["selected_count"],
                                maxgen=options["maxgen"], parallel_workers=1),
                use_taichi=False, parallel_workers=1,
            )
            for key in ("perfect_result", "perfect_parameter", "perfect_a", "perfect_d", "perfect_cl"):
                np.testing.assert_array_equal(getattr(reference, key), getattr(resumed, key))


if __name__ == "__main__":
    unittest.main()

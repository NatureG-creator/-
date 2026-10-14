import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.config import default_simulation_config
from backend.runner import run_simulation


class RunnerTests(unittest.TestCase):
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

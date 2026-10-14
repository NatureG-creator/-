import tempfile
import unittest
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

from backend.config import default_simulation_config
from backend.strict_ga import run_strict_stage
from corrosion_model.ga_优化版 import GAConfig, run_ga
from backend.strict_ga import scientific_settings


def tiny_config():
    config = default_simulation_config()
    config["GEOMETRY_CONFIG"].update(grid_w=5, grid_l=6, grid_n=4, space_xy_um=25, space_z_um=25)
    config["STAGE_GA_CONFIG"].update(F=3, nind=4, selected_count=2, maxgen=3, parallel_workers=1)
    return config


def crash_probe(folder, phase):
    """Exit only this test-created child at an exact durable transaction boundary."""
    from backend import checkpoint as checkpoint_module
    original_replace = checkpoint_module.os.replace

    def replace(source, destination):
        if Path(destination).name == "progress.json":
            candidate = json.loads(Path(source).read_bytes())["state"]
            if phase == "best_metadata" and candidate["best_state"] is not None:
                os._exit(77)  # Large immutable state exists; metadata is still old.
            if phase == "generation_metadata" and candidate["generation"] == 2:
                os._exit(77)  # Selection done in memory; durable RNG still pre-selection.
            if phase == "individual_metadata" and candidate["next_individual"] == 1:
                original_replace(source, destination)
                os._exit(77)  # First individual's metadata is committed.
        original_replace(source, destination)

    checkpoint_module.os.replace = replace
    run_strict_stage(np.array([10, 2, 1, 3, .2, .3]), tiny_config(), 1, Path(folder), "same")
    raise RuntimeError("The crash phase was not reached")


class StrictResumeTests(unittest.TestCase):
    def test_real_child_exit_at_individual_best_and_generation_transactions(self):
        config = tiny_config()
        target = np.array([10, 2, 1, 3, .2, .3])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            baseline = run_strict_stage(target, config, 1, root / "continuous", "same")
            for phase in ("individual_metadata", "best_metadata", "generation_metadata"):
                case = root / phase
                child = subprocess.run(
                    [sys.executable, "-m", "backend.tests.test_strict_ga", "--crash-probe", str(case), phase],
                    cwd=Path(__file__).resolve().parents[2], capture_output=True, timeout=30)
                self.assertEqual(child.returncode, 77, child.stderr.decode(errors="replace"))
                resumed = run_strict_stage(target, config, 1, case, "same")
                for key in ("perfect_result", "perfect_parameter", "perfect_a", "perfect_d", "perfect_cl"):
                    np.testing.assert_array_equal(getattr(baseline, key), getattr(resumed, key))
                self.assertEqual(baseline.generations, resumed.generations)

    def test_two_stages_custom_ga_match_copied_original(self):
        config = tiny_config()
        config["GA_CONFIG"].update(bits_per_param=7, base_px=.7, base_pm=.2, seed=23)
        config["CA_CONFIG"].update(initial_d=6.0, initial_cl=1.0)
        options = config["STAGE_GA_CONFIG"]
        ga = config["GA_CONFIG"]
        reference_previous = strict_previous = None
        with tempfile.TemporaryDirectory() as folder:
            for index, row in enumerate(([10, 2, 1, 3, .2, .3], [12, 3, 1, 4, .2, .3]), 1):
                target = np.asarray(row, dtype=float)
                strict = run_strict_stage(target, config, index, Path(folder) / str(index), "same",
                    a_input=None if strict_previous is None else strict_previous.perfect_a,
                    d_input=None if strict_previous is None else strict_previous.perfect_d,
                    cl_input=None if strict_previous is None else strict_previous.perfect_cl)
                with scientific_settings(config):
                    reference = run_ga(5, 6, 4, row[0], target,
                        None if reference_previous is None else reference_previous.perfect_a,
                        options["F"], index, 25,
                        None if reference_previous is None else reference_previous.perfect_d,
                        None if reference_previous is None else reference_previous.perfect_cl,
                        seed=ga["seed"] + index - 1,
                        config=GAConfig(nind=options["nind"], selected_count=options["selected_count"],
                                        maxgen=options["maxgen"], bits_per_param=ga["bits_per_param"],
                                        base_px=ga["base_px"], base_pm=ga["base_pm"],
                                        decay_rate=ga["decay_rate"], sigma_share=ga["sigma_share"]),
                        lb=np.asarray(config["GA_PARAMETER_LOWER_BOUNDS"]),
                        ub=np.asarray(config["GA_PARAMETER_UPPER_BOUNDS"]),
                        use_taichi=False, parallel_workers=1)
                for key in ("perfect_result", "perfect_parameter", "perfect_a", "perfect_d", "perfect_cl"):
                    np.testing.assert_array_equal(getattr(reference, key), getattr(strict, key))
                reference_previous, strict_previous = reference, strict
    def test_single_stage_uses_independent_settings_and_complete_resume_generation(self):
        config = default_simulation_config()
        config["GEOMETRY_CONFIG"].update(grid_w=5, grid_l=6, grid_n=4)
        config["STAGE_GA_CONFIG"].update(F=3, nind=4, selected_count=2, maxgen=4)
        config["SINGLE_STAGE_GA_CONFIG"].update(F=2, nind=2, selected_count=1, maxgen=2, parallel_workers=1)
        target = np.array([10, 2, 1, 3, .2, .3])
        with tempfile.TemporaryDirectory() as folder:
            self.assertIn("run_mode", __import__("inspect").signature(run_strict_stage).parameters)
            events = []
            result = run_strict_stage(target, config, 1, Path(folder), "same",
                                      run_mode="single", progress=events.append)
            self.assertEqual(events[0]["total_individuals"], 2)
            resumed = run_strict_stage(target, config, 1, Path(folder), "same", run_mode="single")
            self.assertEqual(result.generations, resumed.generations)

    def test_interruption_after_new_best_file_preserves_original_result(self):
        config = default_simulation_config()
        config["GEOMETRY_CONFIG"].update(grid_w=5, grid_l=6, grid_n=4)
        config["STAGE_GA_CONFIG"].update(F=3, nind=4, selected_count=2, maxgen=3)
        target = np.array([10, 2, 1, 3, .2, .3])
        from backend.checkpoint import CheckpointStore
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            baseline = run_strict_stage(target, config, 1, root / "baseline", "same")
            self.assertTrue(hasattr(CheckpointStore, "save_arrays"), "需要不可变最优状态接口")
            original = CheckpointStore.save_arrays

            def interrupt(store, **arrays):
                original(store, **arrays)
                raise InterruptedError("best saved before metadata")

            with patch.object(CheckpointStore, "save_arrays", interrupt):
                with self.assertRaises(InterruptedError):
                    run_strict_stage(target, config, 1, root / "resume", "same")
            resumed = run_strict_stage(target, config, 1, root / "resume", "same")
            for key in ("perfect_result", "perfect_parameter", "perfect_a", "perfect_d", "perfect_cl"):
                np.testing.assert_array_equal(getattr(baseline, key), getattr(resumed, key))

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
    if len(sys.argv) > 1 and sys.argv[1] == "--crash-probe":
        crash_probe(Path(sys.argv[2]), sys.argv[3])
    else:
        unittest.main()

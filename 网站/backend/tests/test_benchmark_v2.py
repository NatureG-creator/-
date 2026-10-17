import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.tests.test_benchmark import request
from backend.benchmark import compare_arrays, prepare_benchmark


class BenchmarkV2Tests(unittest.TestCase):
    def test_empty_seed_list_uses_editable_default_seed(self):
        value = request()
        value["options"].update(seeds=[], seed=123)
        spec = prepare_benchmark(value)
        self.assertEqual(spec["options"]["seeds"], [123])
        self.assertIn("123", spec["populations"])

    def test_matrix_pairs_seeds_workers_and_pool_policies(self):
        from backend.benchmark import build_variants
        value = request()
        value["options"].update(seeds=[8, 9], worker_counts=[2, 3],
                                pool_policies=["recreate", "persistent"], cpu_budget=8)
        original = copy.deepcopy(value)
        spec = prepare_benchmark(value)
        variants = build_variants(spec)
        self.assertEqual(len(variants), 10)
        self.assertEqual(value, original)
        self.assertEqual(len({v["variant_id"] for v in variants}), 10)
        for variant in variants:
            self.assertEqual(variant["baseline_id"], f"numpy_serial__s{variant['seed']}")
        self.assertNotEqual(spec["populations"]["8"], spec["populations"]["9"])

    def test_cpu_budget_rejects_oversubscription(self):
        value = request()
        value["options"].update(threads_per_worker=4, cpu_budget=2)
        with self.assertRaisesRegex(ValueError, "预算"):
            prepare_benchmark(value)

    def test_random_order_is_reproducible_and_keeps_baseline_pairing(self):
        from backend.benchmark import build_variants
        value = request(["numpy_parallel", "taichi_cpu", "taichi_gpu"])
        value["options"].update(order_mode="random", seeds=[8, 9])
        spec = prepare_benchmark(value)
        self.assertEqual(build_variants(spec), build_variants(spec))
        baseline_ids = {v["variant_id"] for v in build_variants(spec) if v["mode"] == "numpy_serial"}
        self.assertTrue(all(v["baseline_id"] in baseline_ids for v in build_variants(spec)))

    def test_categorical_state_must_be_exact_even_within_numeric_tolerance(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            values = {"objv": np.zeros((1, 6)), "a": np.ones((1, 2, 3, 4)),
                      "d": np.zeros((1, 2, 3, 4)), "cl": np.zeros((1, 2, 3))}
            np.savez(root / "left.npz", **values)
            values["a"][0, 0, 0, 0] += 1e-10
            np.savez(root / "right.npz", **values)
            report = compare_arrays(root / "left.npz", root / "right.npz")
            self.assertEqual(report["arrays"]["a"]["mismatch_count"], 1)
            self.assertFalse(report["arrays"]["a"]["within_tolerance"])
            self.assertAlmostEqual(report["arrays"]["a"]["mismatch_fraction"], 1/24)

    def test_short_ga_budget_counts_generations_and_matrix(self):
        value = request()
        value["options"].update(workload="short_ga", generations=3)
        population = prepare_benchmark(request())
        short = prepare_benchmark(value)
        self.assertEqual(short["estimated_work"], population["estimated_work"] * 3)


if __name__ == "__main__":
    unittest.main()

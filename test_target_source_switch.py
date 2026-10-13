"""目标来源开关的最小行为测试。"""

import numpy as np
import unittest

from unified_config import (
    ACTIVE_STAGE_TARGET_DATA,
    MULTI_CASE_CONFIG,
    TARGET_SOURCE,
    manual_stage_data_copy,
)


class TargetSourceSwitchTests(unittest.TestCase):
    def test_default_target_source_is_matlab(self):
        self.assertIn(TARGET_SOURCE, {"matlab", "manual"})


    def test_manual_target_has_original_six_columns(self):
        data = manual_stage_data_copy()
        self.assertEqual(data.ndim, 2)
        self.assertEqual(data.shape[1], 6)
        self.assertTrue(np.array_equal(data, ACTIVE_STAGE_TARGET_DATA))
        self.assertTrue(np.isfinite(data).all())


    def test_invalid_target_source_is_rejected(self):
        from target_source import validate_target_source

        with self.assertRaises(ValueError):
            validate_target_source("other")

    def test_multi_case_config_is_a_disabled_safe_case_list(self):
        self.assertIn("enabled", MULTI_CASE_CONFIG)
        self.assertIn("run_mode", MULTI_CASE_CONFIG)
        self.assertIn(MULTI_CASE_CONFIG["run_mode"], {"single", "sequential", "parallel", "mixed"})
        self.assertIn("sequential_enabled", MULTI_CASE_CONFIG)
        self.assertIn("parallel_enabled", MULTI_CASE_CONFIG)
        self.assertIn("parallel_case_workers", MULTI_CASE_CONFIG)
        self.assertIn("cases", MULTI_CASE_CONFIG)
        self.assertIsInstance(MULTI_CASE_CONFIG["cases"], list)
        for case in MULTI_CASE_CONFIG["cases"]:
            self.assertIsInstance(case, dict)
            self.assertTrue(str(case.get("case_name", "")).strip())
            self.assertTrue(str(case.get("matlab_target", "")).strip())
            self.assertIn(case.get("mode", "sequential"), {"sequential", "parallel"})


if __name__ == "__main__":
    unittest.main()

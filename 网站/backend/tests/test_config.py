import unittest

from backend.config import (default_simulation_config, validate_simulation_config,
                            validate_targets, website_default_simulation_config)


class ConfigTests(unittest.TestCase):
    def test_target_rows_follow_selected_mode(self):
        self.assertEqual(validate_targets([[10, 2, 1, 3, 0.2, 0.3]], "single"), 1)
        with self.assertRaisesRegex(ValueError, "一行"):
            validate_targets([[10, 2, 1, 3, 0.2, 0.3], [12, 3, 1, 4, 0.2, 0.3]], "single")

    def test_invalid_postprocess_is_rejected_before_run(self):
        config = default_simulation_config()
        config["MATLAB_CA_COMPARISON_CONFIG"]["sjb_divisor"] = 0
        with self.assertRaisesRegex(ValueError, "sjb_divisor"):
            validate_simulation_config(config)

    def test_strict_mode_uses_numpy_single_worker(self):
        config = default_simulation_config()
        config["mode"] = "strict"
        config["STAGE_GA_CONFIG"]["parallel_workers"] = 2
        with self.assertRaisesRegex(ValueError, "parallel_workers"):
            validate_simulation_config(config)

    def test_pycharm_mode_defaults_to_numpy_process_pool(self):
        config = website_default_simulation_config()
        self.assertEqual(config["mode"], "pycharm")
        self.assertFalse(config["TAICHI_CONFIG"]["use_taichi"])
        self.assertEqual(config["STAGE_GA_CONFIG"]["parallel_workers"], 10)
        self.assertEqual(config["SINGLE_STAGE_GA_CONFIG"]["parallel_workers"], 10)
        config["mode"] = "pycharm"
        self.assertIs(validate_simulation_config(config), config)
        config["TAICHI_CONFIG"]["use_taichi"] = True
        with self.assertRaisesRegex(ValueError, "use_taichi"):
            validate_simulation_config(config)

    def test_taichi_arch_is_cpu_only(self):
        config = default_simulation_config()
        config["TAICHI_CONFIG"]["arch"] = "gpu"
        with self.assertRaisesRegex(ValueError, "arch"):
            validate_simulation_config(config)

    def test_process_pool_reuse_requires_parallel_non_strict_mode(self):
        config = default_simulation_config()
        config["STAGE_GA_CONFIG"]["reuse_process_pool"] = True
        with self.assertRaisesRegex(ValueError, "严格可复现模式"):
            validate_simulation_config(config)
        config = default_simulation_config()
        config["mode"] = "pycharm"
        config["STAGE_GA_CONFIG"]["reuse_process_pool"] = True
        with self.assertRaisesRegex(ValueError, "parallel_workers 大于1"):
            validate_simulation_config(config)
        config["STAGE_GA_CONFIG"]["parallel_workers"] = 2
        self.assertIs(validate_simulation_config(config), config)


if __name__ == "__main__":
    unittest.main()

"""输入合同回归测试：不启动 CA/GA 或 MATLAB。"""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import savemat

from backend import config as cfg
from backend import targets
from backend.pointcloud_config import catalog, validate_pointcloud_config
from backend.pointcloud_runner import inspect_xyz


class ParameterCatalogTests(unittest.TestCase):
    def test_every_source_constant_has_catalog_and_default(self):
        from backend.parameter_catalog import simulation_catalog
        defaults = cfg.default_simulation_config()
        entries = simulation_catalog()
        source_names = {name for name in vars(cfg.source_config) if name.isupper()}
        self.assertTrue(source_names <= set(defaults))
        roots = {item["path"].split(".")[0] for item in entries}
        self.assertTrue(source_names <= roots)
        for item in entries:
            self.assertTrue({"path", "group", "key", "label", "help", "type", "value", "scope", "editable"} <= set(item))
            self.assertIn(item["type"], {"number", "integer", "boolean", "string", "array", "object", "null"})
        paths = [item for item in entries if item["group"] in {"PATH_CONFIG", "ROOT"}]
        self.assertTrue(paths)
        self.assertTrue(all(item["editable"] for item in paths if item["group"] == "PATH_CONFIG"))
        self.assertTrue(all(not item["editable"] for item in paths if item["group"] == "ROOT"))

    def test_default_workspace_paths_use_research_root_and_numbered_chinese_names(self):
        paths = cfg.default_simulation_config()["PATH_CONFIG"]
        self.assertTrue(all(str(value).startswith("D:\\research\\DATA\\Corrosion modelling\\") for value in paths.values()))
        self.assertTrue(str(paths["inputs"]).endswith("任务输入目录1"))
        self.assertTrue(str(paths["curve_metadata"]).endswith("曲线元信息文件1.csv"))

    def test_path_config_rejects_empty_or_nul_paths(self):
        config = cfg.default_simulation_config()
        config["PATH_CONFIG"]["inputs"] = ""
        with self.assertRaisesRegex(ValueError, "inputs"):
            cfg.validate_simulation_config(config)
        config = cfg.default_simulation_config()
        config["PATH_CONFIG"]["inputs"] = "D:\\研究\x00数据"
        with self.assertRaisesRegex(ValueError, "NUL"):
            cfg.validate_simulation_config(config)

    def test_resource_estimate_is_json_and_scales_with_stages(self):
        from backend.parameter_catalog import estimate_resources
        first = estimate_resources(cfg.default_simulation_config(), 1)
        second = estimate_resources(cfg.default_simulation_config(), 2)
        json.dumps(first, allow_nan=False)
        self.assertTrue(first["estimated"])
        self.assertGreater(first["memory_bytes"], 0)
        self.assertEqual(second["estimated_evaluations"], first["estimated_evaluations"] * 2)
        self.assertTrue(first["recommendations"])

    def test_resource_estimate_counts_taichi_retained_population(self):
        from backend.parameter_catalog import estimate_resources
        config = cfg.default_simulation_config()
        config["mode"] = "fast"
        config["TAICHI_CONFIG"]["use_taichi"] = True
        config["STAGE_GA_CONFIG"]["parallel_workers"] = 1
        estimate = estimate_resources(config)
        geometry = config["GEOMETRY_CONFIG"]
        state_bytes = (geometry["grid_w"] * geometry["grid_l"] * geometry["grid_n"] * 2
                       + geometry["grid_w"] * geometry["grid_l"]) * 8
        self.assertEqual(estimate["retained_population_bytes"], state_bytes * config["STAGE_GA_CONFIG"]["nind"])
        self.assertGreater(estimate["memory_gib"], 7)
        self.assertGreater(estimate["phase_peak_bytes"]["population_evaluation"],
                           estimate["retained_population_bytes"] * 2)
        self.assertEqual(estimate["memory_bytes"], max(estimate["phase_peak_bytes"].values()))
        self.assertFalse(estimate["guaranteed_upper_bound"])

    def test_resource_estimate_selects_single_parameters_and_original_generation_loop(self):
        from backend.parameter_catalog import estimate_resources
        config = cfg.default_simulation_config()
        estimate = estimate_resources(config, 1, "single")
        settings = config["SINGLE_STAGE_GA_CONFIG"]
        self.assertEqual(estimate["estimated_evaluations"], settings["nind"] * (settings["maxgen"] - 1))
        self.assertEqual(estimate["workers"], 1)
        self.assertEqual(estimate["retained_population_bytes"], 0)
        self.assertEqual(estimate["run_mode"], "single")

    def test_catalog_scopes_explain_fields_unconsumed_by_current_task(self):
        from backend.parameter_catalog import simulation_catalog
        entries = {entry["path"]: entry for entry in simulation_catalog()}
        self.assertIn("本任务未使用", entries["FIGURE_CONFIG.surface_elev"]["scope"])
        self.assertIn("本任务未使用", entries["POSTPROCESS_CONFIG.interactive_window_size"]["scope"])
        self.assertIn("适应度", entries["POSTPROCESS_CONFIG.auto_plot_window_size"]["scope"])
        self.assertIn("热图", entries["FIGURE_CONFIG.surface_cmap"]["scope"])
        self.assertIn("10", entries["GA_PARAMETER_LOWER_BOUNDS"]["help"])
        self.assertIn("随机", entries["GA_CONFIG.seed"]["help"])
        self.assertIn("matlab", entries["TARGET_SOURCE"]["help"])

    def test_boolean_array_enum_and_advanced_numeric_validation(self):
        changes = [
            ("TAICHI_CONFIG", "verbose", "false"),
            ("FIGURE_CONFIG", "interactive_figsize", [1]),
            ("TAICHI_CONFIG", "arch", "magic"),
            ("GA_CONFIG", "bits_per_param", 0),
            ("POSTPROCESS_CONFIG", "gaussian_sigma", -1),
            ("GA_CONFIG", "base_pm", 2),
        ]
        for group, key, value in changes:
            with self.subTest(key=key):
                config = cfg.default_simulation_config()
                config[group][key] = value
                with self.assertRaisesRegex(ValueError, key):
                    cfg.validate_simulation_config(config)

    def test_multi_case_editing_supports_any_count_and_modes(self):
        config = cfg.default_simulation_config()
        config["MULTI_CASE_CONFIG"]["cases"] = [
            {"case_name": "first", "matlab_target": "first.mat", "mode": "sequential"},
            {"case_name": "second", "matlab_target": "second.mat", "mode": "parallel"}]
        cfg.validate_simulation_config(config)
        config["MULTI_CASE_CONFIG"]["cases"][0]["mode"] = "invalid"
        with self.assertRaisesRegex(ValueError, "mode"):
            cfg.validate_simulation_config(config)

    def test_web_case_can_select_upload_or_explicit_targets(self):
        config = cfg.default_simulation_config()
        config["MULTI_CASE_CONFIG"]["cases"] = [
            {"case_name": "uploaded", "upload_id": "123", "variable": "target_data", "orientation": "rows",
             "simulation_mode": "staged"},
            {"case_name": "manual", "targets": [[1, 2, 3, 4, 5, 6]]}]
        cfg.validate_simulation_config(config)


class TargetInputTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "targets.mat"

    def test_auto_mat_target_rows_and_switch(self):
        savemat(self.path, {"target_data": np.arange(12).reshape(2, 6),
                            "alternate": np.arange(18).reshape(6, 3)})
        info = targets.inspect_target(self.path)
        self.assertEqual(info["targets"], np.arange(12).reshape(2, 6).tolist())
        self.assertEqual(info["shape"], [2, 6])
        self.assertEqual(info["issues"], [])
        self.assertGreaterEqual(info["reading_seconds"], 0)
        switched = targets.inspect_target(self.path, "alternate")
        self.assertEqual(switched["targets"], np.arange(18).reshape(6, 3).T.tolist())
        self.assertEqual(targets.load_targets(self.path, "alternate"), switched["targets"])

    def test_multiple_candidates_need_selection_without_known_name(self):
        savemat(self.path, {"one": np.ones((2, 6)), "two": np.ones((3, 6))})
        info = targets.inspect_target(self.path)
        self.assertIsNone(info["selected"])
        self.assertTrue(info["issues"])
        with self.assertRaisesRegex(ValueError, "变量"):
            targets.load_targets(self.path)

    def test_square_requires_orientation_and_reports_nonfinite_position(self):
        matrix = np.arange(36, dtype=float).reshape(6, 6)
        savemat(self.path, {"target_data": matrix})
        with self.assertRaisesRegex(ValueError, "方向"):
            targets.load_targets(self.path)
        self.assertEqual(targets.load_targets(self.path, orientation="columns"), matrix.T.tolist())
        matrix[1, 3] = np.nan
        savemat(self.path, {"target_data": matrix})
        info = targets.inspect_target(self.path, orientation="rows")
        json.dumps(info, allow_nan=False)
        self.assertTrue(any("第2行第4列" in issue for issue in info["issues"]))
        with self.assertRaisesRegex(ValueError, "第2行第4列"):
            targets.load_targets(self.path, orientation="rows")

    def test_text_nonfinite_reports_column_and_header_handles_blanks(self):
        path = self.path.with_suffix(".csv")
        path.write_text("\nmean,nonuniform,ratio,depth,s1,s2\n1,2,nan,4,5,6\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "第3行第3列"):
            targets.load_targets(path)

    def test_calibration_false_rejected_even_when_six_values_finite(self):
        savemat(self.path, {"target_data": np.ones((1, 6)), "calibration_ready": False,
                            "calibration_issues": np.array(["参考面未知"], dtype=object)})
        info = targets.inspect_target(self.path)
        self.assertFalse(info["calibration_ready"])
        self.assertEqual(info["targets"], [[1.] * 6])
        self.assertEqual(info["calibration_issues"], ["参考面未知"])
        with self.assertRaisesRegex(ValueError, "calibration_ready=false"):
            targets.load_targets(self.path)

    def test_square_inspection_exposes_original_shape_when_ambiguous(self):
        savemat(self.path, {"target_data": np.ones((6, 6))})
        self.assertEqual(targets.inspect_target(self.path)["shape"], [6, 6])


class PointCloudContractTests(unittest.TestCase):
    def test_pointcloud_catalog_contains_labels_types_and_scope(self):
        for item in catalog():
            self.assertTrue({"label", "type", "scope"} <= set(item))
            self.assertNotIn("190 mm", item["label"])
            self.assertNotIn("50 mm", item["label"])

    def test_small_valid_columns_and_all_boolean_array_types(self):
        config = validate_pointcloud_config({"reference": {"flat_column_count": 2, "corrosion_column_count": 3},
                                             "preprocessing": {"trim_edge_rows": 0}})
        self.assertEqual(config["reference"]["corrosion_column_count"], 3)
        for item in catalog():
            if not item["editable"]:
                continue
            if isinstance(item["value"], bool):
                with self.subTest(key=item["key"]), self.assertRaises(ValueError):
                    validate_pointcloud_config({item["group"]: {item["key"]: "false"}})
            if isinstance(item["value"], list):
                with self.subTest(key=item["key"]), self.assertRaises(ValueError):
                    validate_pointcloud_config({item["group"]: {item["key"]: [False] * len(item["value"])}})

    def test_bad_columns_enums_and_neighborhood_rejected(self):
        invalid = [
            {"reference": {"flat_column_count": 2.5}},
            {"reference": {"flat_height_ratio": 2}},
            {"preprocessing": {"interpolation_method": "invalid"}},
            {"pit_detection": {"neighborhood": [2, 3]}},
            {"figure": {"surface_view": [0, float("inf")]}},
        ]
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate_pointcloud_config(config)

    def test_default_apdl_spacing_follows_overridden_grid(self):
        config = validate_pointcloud_config({"preprocessing": {"grid_resolution_mm": 0.2}})
        self.assertEqual(config["apdl"]["dx_mm"], 0.2)
        self.assertEqual(config["apdl"]["dy_mm"], 0.2)

    def test_xyz_reports_reading_time_and_header_after_blank(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "small.xyz"
            path.write_text("\nx y z\n0 0 1\n2 0 2\n0 3 3\n", encoding="utf-8")
            info = inspect_xyz(path)
            self.assertEqual(info["size_mm"], [2, 3])
            self.assertGreaterEqual(info["reading_seconds"], 0)

    def test_preview_samples_are_actual_points_and_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "large.xyz"
            path.write_text("\n".join(f"{i} {i+1} {i+2}" for i in range(2000)), encoding="utf-8")
            info = inspect_xyz(path)
            self.assertEqual(len(info["sample_points"]), 1000)
            self.assertTrue(info["sample_only"])
            self.assertTrue(all(point[1] == point[0]+1 and point[2] == point[0]+2
                                for point in info["sample_points"]))

    def test_matlab_output_root_contract_and_original_formula(self):
        root = Path(__file__).resolve().parents[2] / "matlab"
        script = (root / "step00_corrosion_config.m").read_text(encoding="utf-8")
        self.assertIn("output_root = getenv('CORROSION_OUTPUT_BASE')", script)
        main = (root / "untitled.m").read_text(encoding="utf-8")
        self.assertIn("fullfile(cfg.project_root", main)
        self.assertIn("ismember(points50(:,1:3),points190(:,1:3),'rows')", main)
        formula = (root / "jisuan_190.m").read_text(encoding="utf-8")
        self.assertIn("max(Z_a(:))-min(Z_a(:))", formula)
        self.assertIn("junyunfushi = Z_fushimian - Z_pingtanmian", formula)
        self.assertIn("max(Z_b(:)", formula)


if __name__ == "__main__":
    unittest.main()

import unittest

from backend.pointcloud_config import catalog, validate_pointcloud_config


class PointCloudConfigTests(unittest.TestCase):
    def test_every_source_setting_is_exposed(self):
        entries = catalog()
        fields = {(item["group"], item["key"]) for item in entries}
        self.assertIn(("preprocessing", "grid_resolution_mm"), fields)
        self.assertIn(("figure", "surface_clim"), fields)
        self.assertIn(("input", "point_cloud_190_pattern"), fields)
        self.assertIn(("output", "apdl_z_txt"), fields)
        self.assertGreaterEqual(len(fields), 55)

    def test_invalid_grid_is_rejected(self):
        config = {"preprocessing": {"grid_resolution_mm": 0}}
        with self.assertRaisesRegex(ValueError, "grid_resolution_mm"):
            validate_pointcloud_config(config)


if __name__ == "__main__":
    unittest.main()

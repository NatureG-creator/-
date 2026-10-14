import tempfile
import unittest
from pathlib import Path

from backend.pointcloud_runner import inspect_xyz, run_pointcloud


class PointCloudRunnerTests(unittest.TestCase):
    def test_xyz_dimensions_are_read_from_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "sample.xyz"
            source.write_text("0 0 1\n5 0 2\n0 7 3\n", encoding="utf-8")
            result = inspect_xyz(source)
            self.assertEqual(result["points"], 3)
            self.assertEqual(result["size_mm"], [5.0, 7.0])

    def test_matlab_unavailable_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "sample.xyz"
            source.write_text("0 0 1\n5 0 2\n0 7 3\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "MATLAB"):
                run_pointcloud(Path(folder) / "job", source, source, {}, matlab_bin=Path(folder) / "missing.exe")


if __name__ == "__main__":
    unittest.main()

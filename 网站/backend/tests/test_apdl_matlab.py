import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.io import savemat

from backend.apdl_matlab import convert_uploaded_matrix, inspect_mat_variables
from backend.server import make_server


class ApdlMatlabConversionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.server = make_server("127.0.0.1", 0, Path(self.folder.name))

    def tearDown(self):
        self.server.server_close()
        self.folder.cleanup()

    def _upload(self, name, data):
        return self.server.upload(name, io.BytesIO(data), len(data))["id"]

    def test_conversion_registers_xyz_outputs_and_preserves_column_order(self):
        upload_id = self._upload("surface.csv", b"1,2,3\n4,5,6\n")

        output_dir = Path(self.server.runtime) / "matlab_apdl" / upload_id

        def fake_run(command, **kwargs):
            self.assertIn("'surface_mm'", command[-1])
            np.savetxt(output_dir / "DIANYUN_X.txt", [0, 0, .3, .3, .6, .6], fmt="%.12g")
            np.savetxt(output_dir / "DIANYUN_Y.txt", [0, .3, 0, .3, 0, .3], fmt="%.12g")
            np.savetxt(output_dir / "DIANYUN_Z.txt", [1, 4, 2, 5, 3, 6], fmt="%.12g")
            (output_dir / "conversion_summary.json").write_text(json.dumps({
                "conversion_mode": "surface_mm", "input_shape": [2, 3], "shape": [2, 3],
                "input_range": [1, 6], "z_range_mm": [1, 6], "max_relative_depth_mm": 5,
            }), encoding="utf-8")
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch("backend.apdl_matlab.find_matlab", return_value="matlab.exe"), patch(
            "backend.apdl_matlab.subprocess.run", side_effect=fake_run
        ):
            result = convert_uploaded_matrix(self.server, {
                "upload_id": upload_id, "dx_mm": .3, "dy_mm": .3,
                "x_start_mm": 0, "y_start_mm": 0,
            })

        self.assertEqual(result["shape"], [2, 3])
        self.assertEqual(result["conversion"]["conversion_mode"], "surface_mm")
        self.assertEqual(set(result["files"]), {"x", "y", "z"})
        for item in result["files"].values():
            self.assertTrue((self.server.runtime / "uploads" / item["id"] / "metadata.json").is_file())

    def test_baseline_mat_is_recognized_without_guessing_its_units(self):
        data = io.BytesIO()
        savemat(data, {"baseline": np.arange(6.).reshape(2, 3), "title": "not numeric"})
        upload_id = self._upload("baseline.mat", data.getvalue())
        _, source = self.server.get_upload(upload_id)
        self.assertEqual(inspect_mat_variables(source), [{"name": "baseline", "shape": [2, 3]}])

    def test_layer_mode_passes_explicit_scale_and_back_direction_to_matlab(self):
        upload_id = self._upload("surface.csv", b"1,2,3\n4,5,6\n")
        output_dir = self.server.runtime / "matlab_apdl" / upload_id
        def fake_run(command, **kwargs):
            self.assertIn("'baseline_cells',0.050000000000000003,'back'", command[-1])
            np.savetxt(output_dir / "DIANYUN_X.txt", [0, 0, 0, .3, .3, .3])
            np.savetxt(output_dir / "DIANYUN_Y.txt", [0, .3, .6, 0, .3, .6])
            np.savetxt(output_dir / "DIANYUN_Z.txt", [.05, .1, .15, .2, .25, .3])
            (output_dir / "conversion_summary.json").write_text(json.dumps({
                "conversion_mode": "baseline_cells", "cell_thickness_mm": .05,
                "input_shape": [2, 3], "shape": [3, 2], "input_range": [1, 6],
                "z_range_mm": [.05, .3], "max_relative_depth_mm": .25,
            }), encoding="utf-8")
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        with patch("backend.apdl_matlab.find_matlab", return_value="matlab.exe"), patch(
            "backend.apdl_matlab.subprocess.run", side_effect=fake_run
        ):
            result = convert_uploaded_matrix(self.server, {"upload_id": upload_id, "dx_mm": .3,
                "dy_mm": .3, "conversion_mode": "baseline_cells", "cell_thickness_mm": .05,
                "coordinate_direction": "back"})
        self.assertEqual(result["shape"], [3, 2])
        self.assertEqual(result["conversion"]["cell_thickness_mm"], .05)

    def test_rejects_invalid_conversion_settings_before_matlab(self):
        upload_id = self._upload("surface.csv", b"1,2\n3,4\n")
        base = {"upload_id": upload_id, "dx_mm": .3, "dy_mm": .3}
        cases = [{"conversion_mode": "unknown"}, {"coordinate_direction": "unknown"}]
        cases += [{"conversion_mode": "baseline_cells", "cell_thickness_mm": value}
                  for value in (0, -1, None, "", "NaN", float("inf"), True)]
        with patch("backend.apdl_matlab.subprocess.run") as run:
            for case in cases:
                with self.subTest(case=case), self.assertRaises(ValueError):
                    convert_uploaded_matrix(self.server, {**base, **case})
            run.assert_not_called()

    def test_rejects_invalid_spacing_before_calling_matlab(self):
        upload_id = self._upload("surface.csv", b"1,2\n3,4\n")
        with self.assertRaisesRegex(ValueError, "dx_mm"):
            convert_uploaded_matrix(self.server, {"upload_id": upload_id, "dx_mm": 0, "dy_mm": .3})

    def test_matlab_unavailable_has_actionable_error(self):
        upload_id = self._upload("surface.csv", b"1,2\n3,4\n")
        with patch("backend.apdl_matlab.find_matlab", return_value=None):
            with self.assertRaisesRegex(ValueError, "MATLAB"):
                convert_uploaded_matrix(self.server, {"upload_id": upload_id, "dx_mm": .3, "dy_mm": .3})


if __name__ == "__main__":
    unittest.main()

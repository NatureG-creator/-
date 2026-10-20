import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from backend.apdl_matlab import convert_uploaded_matrix
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
            np.savetxt(output_dir / "DIANYUN_X.txt", [0, .3, 0, .3], fmt="%.12g")
            np.savetxt(output_dir / "DIANYUN_Y.txt", [0, 0, .3, .3], fmt="%.12g")
            np.savetxt(output_dir / "DIANYUN_Z.txt", [1, 4, 2, 5], fmt="%.12g")
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch("backend.apdl_matlab.find_matlab", return_value="matlab.exe"), patch(
            "backend.apdl_matlab.subprocess.run", side_effect=fake_run
        ):
            result = convert_uploaded_matrix(self.server, {
                "upload_id": upload_id, "dx_mm": .3, "dy_mm": .3,
                "x_start_mm": 0, "y_start_mm": 0,
            })

        self.assertEqual(result["shape"], [2, 2])
        self.assertEqual(set(result["files"]), {"x", "y", "z"})
        for item in result["files"].values():
            self.assertTrue((self.server.runtime / "uploads" / item["id"] / "metadata.json").is_file())

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

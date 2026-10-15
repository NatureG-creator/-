import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import loadmat, savemat

from backend.finite_element_export import (
    create_surface_bundle,
    validate_surface_matrix,
)


class FiniteElementExportTests(unittest.TestCase):
    def test_validate_surface_matrix_rejects_non_finite_values(self):
        with self.assertRaises(ValueError):
            validate_surface_matrix(np.array([[1.0, np.nan]]))

    def test_measured_bundle_keeps_shape_and_writes_manifest_and_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "measured.mat"
            output = root / "output"
            matrix = np.arange(6, dtype=float).reshape(2, 3)
            savemat(source, {"F_filled": matrix})

            result = create_surface_bundle(
                "measured", source, output,
                {"input_variable": "F_filled", "output_variable": "F_filled",
                 "space_z_um": 25.0, "grid_spacing_mm": 0.05,
                 "origin_x_mm": 0.0, "origin_y_mm": 0.0, "precision": "%.6f"},
            )

            self.assertEqual(result["shape"], [2, 3])
            self.assertEqual(result["output_variable"], "F_filled")
            self.assertTrue((output / "F_filled.mat").is_file())
            self.assertTrue((output / "surface.csv").is_file())
            self.assertTrue((output / "coordinates.csv").is_file())
            self.assertTrue((output / "finite_element_manifest.json").is_file())
            self.assertTrue((output / "finite_element_input_bundle.zip").is_file())
            np.testing.assert_array_equal(loadmat(output / "F_filled.mat")["F_filled"], matrix)
            manifest = json.loads((output / "finite_element_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["shape"], [2, 3])
            self.assertEqual(manifest["source"]["kind"], "measured")

    def test_simulation_bundle_converts_first_metal_layer_to_mm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "simulation.npz"
            output = root / "output"
            state = np.zeros((2, 3, 5), dtype=np.uint8)
            state[:, :, 2] = 1
            state[0, 0, 1] = 1
            np.savez(source, perfect_a=state)

            result = create_surface_bundle(
                "simulation", source, output,
                {"input_variable": None, "output_variable": "Z_filled",
                 "space_z_um": 25.0, "grid_spacing_mm": 0.05,
                 "origin_x_mm": 0.0, "origin_y_mm": 0.0, "precision": "%.6f"},
            )

            self.assertEqual(result["shape"], [2, 3])
            matrix = loadmat(output / "Z_filled.mat")["Z_filled"]
            self.assertAlmostEqual(float(matrix[0, 0]), 0.025)
            self.assertAlmostEqual(float(matrix[1, 1]), 0.05)


if __name__ == "__main__":
    unittest.main()

"""APDL MAT 导出器的最小测试。"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import loadmat, savemat

from export_apdl_mat import load_measured_matrix, surface_from_ca_state


class ExportApdlMatTests(unittest.TestCase):
    def test_surface_from_ca_state_keeps_xy_and_uses_first_metal_layer(self):
        state = np.zeros((2, 3, 5), dtype=float)
        state[:, :, 2] = 1.0
        state[0, 0, 1] = 1.0

        result = surface_from_ca_state(state, space_z_um=25.0)

        self.assertEqual(result.shape, (2, 3))
        self.assertAlmostEqual(float(result[0, 0]), 0.025)
        self.assertAlmostEqual(float(result[1, 1]), 0.050)

    def test_measured_loader_preserves_variable_and_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "Fanmian.mat"
            matrix = np.arange(12, dtype=float).reshape(3, 4)
            savemat(source, {"F_filled": matrix})

            name, loaded = load_measured_matrix(source)

            self.assertEqual(name, "F_filled")
            np.testing.assert_array_equal(loaded, matrix)


if __name__ == "__main__":
    unittest.main()

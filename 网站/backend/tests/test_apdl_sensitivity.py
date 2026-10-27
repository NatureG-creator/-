import unittest

from backend.apdl_sensitivity import _meshes, _times, _with_deltas


class ApdlSensitivityTests(unittest.TestCase):
    def test_default_matrix_has_three_meshes_and_two_times(self):
        meshes = _meshes(None)
        times = _times(None)
        self.assertEqual([item['label'] for item in meshes], ['coarse', 'baseline', 'fine'])
        self.assertEqual(times, [0.002, 0.004])

    def test_mesh_validation_rejects_even_face_nodes(self):
        with self.assertRaises(ValueError):
            _meshes([{'label': 'bad', 'nx': 20, 'ny': 3, 'layers': 2},
                     {'label': 'ok', 'nx': 41, 'ny': 5, 'layers': 4}])

    def test_deltas_use_baseline_case(self):
        rows = [
            {'peak_force_n': 90., 'peak_engineering_strain': .1, 'separation_displacement_mm': 1.},
            {'peak_force_n': 100., 'peak_engineering_strain': .2, 'separation_displacement_mm': 2.},
        ]
        _with_deltas(rows, rows[1])
        self.assertAlmostEqual(rows[0]['peak_force_n_delta_pct'], -10.)
        self.assertAlmostEqual(rows[0]['peak_engineering_strain_delta_pct'], -50.)
        self.assertEqual(rows[1]['separation_displacement_mm_delta_pct'], 0.)


if __name__ == '__main__':
    unittest.main()

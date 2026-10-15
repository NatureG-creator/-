import unittest

import numpy as np

from backend.apdl_geometry import build_geometry, normalise_options


class APDLGeometryTests(unittest.TestCase):
    def test_output_policy_survives_geometry_option_normalisation(self):
        options = {'corrosion_mode': 'flat', 'result_save_mode': 'selected',
                   'field_output_times': [.2, .8, 1]}
        normalised = normalise_options(options)
        self.assertEqual(normalised['result_save_mode'], 'selected')
        self.assertEqual(normalised['field_output_times'], [.2, .8, 1])
        g = build_geometry(None, None, options)
        self.assertEqual(g['options']['field_output_times'], [.2, .8, 1])
        with self.assertRaises(ValueError):
            normalise_options({'result_save_mode': 'selected', 'field_output_times': [.8, .2, 1]})

    def test_double_face_remaining_and_non_square_axes(self):
        g = build_geometry(np.full((2, 3), .8), np.full((2, 3), .5), {
            'corrosion_mode': 'double_independent', 'dx_mm': 2, 'dy_mm': 3,
            'origin_x_mm': 10, 'origin_y_mm': -4, 'layers': 2})
        np.testing.assert_allclose(g['remaining'], 4.7)
        np.testing.assert_equal(g['x'], [10, 12, 14])
        np.testing.assert_equal(g['y'], [-4, -1])
        self.assertEqual(g['nodes'].shape, (18, 4))
        self.assertEqual(g['elements'].shape, (4, 9))
        self.assertAlmostEqual(g['stats']['remaining_volume_mm3'], 4*3*4.7)
        self.assertEqual(g['options']['nx'], 3)
        self.assertEqual(g['options']['length_mm'], 4)
        np.testing.assert_allclose(g['nodes'][:6, 3], .5)
        np.testing.assert_allclose(g['nodes'][-6:, 3], 5.2)

    def test_connectivity_has_positive_orientation_and_exact_counts(self):
        g = build_geometry(np.array([[.1, .3, .2], [.4, .8, .5]]), None,
                           {'layers': 3, 'dx_mm': .5, 'dy_mm': 2})
        self.assertEqual(len(g['nodes']), 24)
        self.assertEqual(len(g['elements']), 6)
        xyz = g['nodes'][:, 1:]
        for element in g['elements'][:, 1:]:
            p = xyz[element.astype(int)-1]
            jac = np.array([p[1]-p[0], p[3]-p[0], p[4]-p[0]])
            self.assertGreater(np.linalg.det(jac), 0)
        self.assertGreater(g['stats']['min_cell_volume_mm3'], 0)

    def test_mode_semantics_do_not_infer_double_independent(self):
        top = np.array([[.2, .3], [.4, .5]])
        g = build_geometry(top, None, {'corrosion_mode': 'double_symmetric'})
        np.testing.assert_array_equal(g['bottom_depth'], top)
        g = build_geometry(None, top, {'corrosion_mode': 'single_bottom'})
        np.testing.assert_array_equal(g['top_depth'], np.zeros_like(top))
        with self.assertRaises(ValueError):
            build_geometry(top, None, {'corrosion_mode': 'double_independent'})
        with self.assertRaises(ValueError):
            build_geometry(top, np.zeros((3, 2)), {'corrosion_mode': 'double_independent'})

    def test_flat_analytical_reference_is_labelled_and_corroded_has_none(self):
        g = build_geometry(None, None, {'corrosion_mode': 'flat', 'length_mm': 100,
                                     'width_mm': 20, 'nx': 3, 'ny': 2})
        self.assertEqual(g['stats']['analytic_stiffness_n_per_mm'], 206000*120/100)
        self.assertEqual(g['stats']['analytic_force_n'], 206000*120*.1/100)
        self.assertNotIn('analytic_force_n', build_geometry(np.zeros((2, 2)), None, {})['stats'])

    def test_invalid_material_arrays_and_piercing_are_rejected(self):
        for value in (np.zeros((1, 2)), np.zeros((2, 2), dtype=bool),
                      np.full((2, 2), np.nan), np.full((2, 2), -.01),
                      np.full((2, 2), 6)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_geometry(value, None, {})
        for options in ({'layers': True}, {'dx_mm': 0}, {'E_MPa': 0},
                        {'poisson_ratio': .5}, {'tangent_MPa': 206000},
                        {'target_displacement_mm': -1}, {'nx': 2.5},
                        {'corrosion_mode': []}, {'material_model': {}},
                        {'boundary_mode': ['poisson_free']}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                normalise_options(options)

    def test_resource_limit_is_checked_before_grid_allocation(self):
        with self.assertRaisesRegex(ValueError, '节点|单元'):
            build_geometry(None, None, {'corrosion_mode': 'flat', 'nx': 100000,
                                      'ny': 100000, 'layers': 3})

    def test_derived_nominal_area_must_remain_finite(self):
        with self.assertRaisesRegex(ValueError, '面积|体积'):
            build_geometry(None, None, {'corrosion_mode': 'flat', 'nx': 2, 'ny': 2,
                                      'length_mm': 1e-200, 'width_mm': 1e200,
                                      'thickness_mm': 1e200})

    def test_multilinear_curve_requires_explicit_softening_permission(self):
        valid = {'material_model': 'multilinear_iso', 'plastic_curve': [[0, 235], [.01, 250], [.02, 240]]}
        with self.assertRaisesRegex(ValueError, '负斜率|下降'):
            normalise_options(valid)
        accepted = normalise_options(dict(valid, allow_negative_slope=True))
        self.assertEqual(accepted['plastic_curve'][-1], [.02, 240])
        for curve in (None, [[.01, 235], [.02, 250]], [[0, 235], [0, 250]], [[0, 235], [.01, 0]], [[0, True], [.01, 240]]):
            with self.subTest(curve=curve), self.assertRaises(ValueError):
                normalise_options({'material_model': 'multilinear_iso', 'plastic_curve': curve})

    def test_load_substep_bounds_are_consistent(self):
        o = normalise_options({'substeps': 100, 'max_substeps': 450, 'min_substeps': 50})
        self.assertEqual(o['min_substeps'], 50)
        for options in ({'substeps': 10, 'max_substeps': 5}, {'substeps': 10, 'min_substeps': 20}):
            with self.assertRaises(ValueError):
                normalise_options(options)

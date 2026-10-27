import unittest
from collections import Counter
from itertools import combinations

import numpy as np

from backend.apdl_geometry import build_geometry, normalise_options


class APDLGeometryTests(unittest.TestCase):
    def test_tetra_flat_volume_and_boundary_have_no_missing_or_overlapping_cells(self):
        for mesh_type in ('solid187_tetra', 'solid285_tetra'):
            with self.subTest(mesh_type=mesh_type):
                g = build_geometry(None, None, dict(corrosion_mode='flat', nx=3, ny=3,
                    length_mm=2, width_mm=2, thickness_mm=2, layers=3, mesh_type=mesh_type))
                corners = g['elements'][:, 1:5]
                p = g['nodes'][corners-1, 1:]
                volumes = np.linalg.det(p[:, 1:]-p[:, :1])/6
                self.assertTrue(np.all(volumes > 0))
                self.assertAlmostEqual(float(volumes.sum()), 8., places=10)
                self.assertAlmostEqual(g['stats']['remaining_volume_mm3'], float(volumes.sum()))
                faces = Counter(tuple(sorted(face)) for tet in corners for face in combinations(tet, 3))
                self.assertTrue(all(count in (1, 2) for count in faces.values()))
                for face, count in faces.items():
                    if count == 1:
                        xyz = g['nodes'][np.asarray(face)-1, 1:]
                        self.assertTrue(any(np.allclose(xyz[:, axis], bound, atol=1e-10, rtol=0)
                            for axis in range(3) for bound in (0., 2.)), face)

    def test_tetra_preserves_all_input_surface_corners_and_triangular_volume(self):
        top = np.array([[.1, .6, .2], [.4, 1.1, .7]])
        bottom = np.array([[.05, .1, .2], [.3, .1, .15]])
        for mode in ('single_top', 'single_bottom', 'double_independent', 'double_symmetric'):
            with self.subTest(mode=mode):
                g = build_geometry(top, bottom, dict(corrosion_mode=mode,
                    mesh_type='solid187_tetra', dx_mm=.4, dy_mm=.5, layers=2))
                remaining = g['remaining']
                expected = .4*.5/6 * np.sum(2*remaining[:-1, :-1]+remaining[:-1, 1:]
                    +2*remaining[1:, 1:]+remaining[1:, :-1])
                self.assertAlmostEqual(g['stats']['remaining_volume_mm3'], expected, places=10)
                xyz = g['nodes'][:, 1:]
                for j, y in enumerate(g['y']):
                    for i, x in enumerate(g['x']):
                        for z in (g['bottom_depth'][j,i], 6-g['top_depth'][j,i]):
                            self.assertTrue(np.any(np.all(xyz == [x,y,z], axis=1)))

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

    def test_mapping_profiles_are_recorded_and_validated(self):
        for profile in ('manual', 'single_top', 'double_strict', 'double_common_xy', 'double_patch'):
            with self.subTest(profile=profile):
                self.assertEqual(normalise_options({'mapping_profile': profile})['mapping_profile'], profile)
        with self.assertRaisesRegex(ValueError, 'mapping_profile'):
            normalise_options({'mapping_profile': 'legacy_script_file'})

    def test_force_displacement_plot_defaults_on_and_accepts_only_boolean(self):
        self.assertTrue(normalise_options({})['export_force_displacement_plot'])
        self.assertFalse(normalise_options({'export_force_displacement_plot': False})[
            'export_force_displacement_plot'])
        for value in (0, 1, 'false', None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, '布尔值'):
                normalise_options({'export_force_displacement_plot': value})

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

    def test_local_corrosion_is_embedded_without_rescaling_on_full_plate(self):
        depth = np.array([[.1, .2, .3], [.4, .5, .6]])
        g = build_geometry(depth, None, {
            'corrosion_mode': 'single_top', 'local_corrosion': True,
            'length_mm': 8, 'width_mm': 4, 'dx_mm': 1, 'dy_mm': 1,
            'layers': 2,
        })
        self.assertEqual((g['stats']['nx'], g['stats']['ny']), (9, 5))
        self.assertEqual(g['stats']['length_mm'], 8)
        self.assertEqual(g['stats']['width_mm'], 4)
        self.assertEqual(g['corrosion_region']['x_range_mm'], [3, 5])
        self.assertEqual(g['corrosion_region']['y_range_mm'], [2, 3])
        np.testing.assert_array_equal(g['top_depth'][2:4, 3:6], depth)
        self.assertEqual(np.count_nonzero(g['top_depth']), np.count_nonzero(depth))
        self.assertEqual(float(g['top_depth'][:2].sum()+g['top_depth'][4:].sum()), 0)
        self.assertEqual(float(g['top_depth'][:, :3].sum()+g['top_depth'][:, 6:].sum()), 0)
        self.assertEqual(g['options']['patch_offset_x_mm'], 3)
        self.assertEqual(g['options']['patch_offset_y_mm'], 2)

    def test_local_corrosion_explicit_offset_and_invalid_placement(self):
        depth = np.ones((2, 3))*.25
        options = {'corrosion_mode': 'single_bottom', 'local_corrosion': True,
                   'length_mm': 8, 'width_mm': 4, 'dx_mm': 1, 'dy_mm': 1,
                   'patch_offset_x_mm': 5, 'patch_offset_y_mm': 3}
        g = build_geometry(None, depth, options)
        self.assertEqual(g['corrosion_region']['x_range_mm'], [5, 7])
        self.assertEqual(g['corrosion_region']['y_range_mm'], [3, 4])
        np.testing.assert_array_equal(g['bottom_depth'][3:5, 5:8], depth)
        for override in ({'patch_offset_x_mm': 7}, {'patch_offset_x_mm': 5.5},
                         {'length_mm': 8.2}, {'corrosion_mode': 'flat'}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                build_geometry(None if override.get('corrosion_mode') != 'flat' else None,
                    None if override.get('corrosion_mode') == 'flat' else depth,
                    dict(options, **override))

    def test_local_patch_rotation_swaps_non_square_axes_and_transforms_both_faces(self):
        top = np.array([[.1, .2, .3], [.4, .5, .6]], dtype=float)
        bottom = top + .1
        g = build_geometry(top, bottom, {
            'corrosion_mode': 'double_independent', 'local_corrosion': True,
            'length_mm': 4, 'width_mm': 4, 'dx_mm': 1, 'dy_mm': 2,
            'patch_rotation_deg': 90, 'patch_flip_x': True, 'patch_flip_y': True,
            'layers': 2,
        })
        expected = np.flipud(np.fliplr(np.rot90(top)))
        np.testing.assert_array_equal(g['top_depth'][1:4, 0:2], expected)
        np.testing.assert_array_equal(g['bottom_depth'][1:4, 0:2], expected + .1)
        self.assertEqual(g['options']['dx_mm'], 2)
        self.assertEqual(g['options']['dy_mm'], 1)
        self.assertEqual(g['corrosion_region']['rotation_deg'], 90)
        self.assertTrue(g['corrosion_region']['flip_x'])
        self.assertTrue(g['corrosion_region']['flip_y'])

    def test_local_patch_rotation_rejects_non_integer_and_boolean_angles(self):
        for angle in (90.0, True, False, 45, '90'):
            with self.subTest(angle=angle), self.assertRaises(ValueError):
                normalise_options({'patch_rotation_deg': angle})

    def test_local_corrosion_switch_is_strict_and_default_path_stays_source_sized(self):
        with self.assertRaisesRegex(ValueError, '布尔值'):
            normalise_options({'local_corrosion': 1})
        g = build_geometry(np.ones((2, 3))*.1, None, {
            'corrosion_mode': 'single_top', 'dx_mm': 1, 'dy_mm': 1,
        })
        self.assertEqual((g['stats']['length_mm'], g['stats']['width_mm']), (2, 1))
        self.assertIsNotNone(g['corrosion_region'])

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

    def test_single_end_center_uses_actual_local_mid_thickness(self):
        g = build_geometry(np.full((5, 5), .2), None, {
            'corrosion_mode': 'single_top', 'boundary_mode': 'single_end_center',
            'dx_mm': 1, 'dy_mm': 1, 'layers': 2, 'tensile_direction': 'X'})
        anchors = g['stats']['end_center_anchors']
        self.assertEqual([a['name'] for a in anchors], ['A', 'B'])
        np.testing.assert_allclose([a['point'][2] for a in anchors], [2.9, 2.9])
        self.assertEqual(anchors[0]['dofs'], ['UY', 'UZ'])
        self.assertEqual(anchors[1]['dofs'], ['UZ'])
        self.assertTrue(np.array_equal(g['top_depth'], np.full((5, 5), .2)))

        y = build_geometry(np.full((5, 5), .2), None, {
            'corrosion_mode': 'single_top', 'boundary_mode': 'single_end_center',
            'dx_mm': 1, 'dy_mm': 1, 'layers': 2, 'tensile_direction': 'Y'})
        self.assertEqual([a['point'][:2] for a in y['stats']['end_center_anchors']], [[2., 0.], [4., 0.]])

    def test_single_end_center_rejects_missing_center_grid_lines(self):
        with self.assertRaisesRegex(ValueError, '横向.*奇数'):
            build_geometry(np.zeros((4, 5)), None, {
                'corrosion_mode': 'single_top', 'boundary_mode': 'single_end_center',
                'dx_mm': 1, 'dy_mm': 1, 'layers': 2})
        with self.assertRaisesRegex(ValueError, '厚度.*偶数'):
            normalise_options({'boundary_mode': 'single_end_center', 'layers': 3})

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
        y = build_geometry(None, None, {'corrosion_mode': 'flat', 'length_mm': 100,
            'width_mm': 20, 'nx': 3, 'ny': 2, 'tensile_direction': 'Y'})
        self.assertEqual(y['stats']['nominal_area_mm2'], 600)
        self.assertEqual(y['stats']['analytic_stiffness_n_per_mm'], 206000*600/20)
        self.assertEqual(y['stats']['analytic_force_n'], 206000*600*.1/20)
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
                        {'boundary_mode': ['poisson_free']}, {'tensile_direction': 'Z'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                normalise_options(options)

    def test_grip_lengths_are_nonnegative_finite_values(self):
        defaults = normalise_options({})
        self.assertEqual(defaults['grip_length_fixed_mm'], 0.)
        self.assertEqual(defaults['grip_length_loaded_mm'], 0.)
        for key in ('grip_length_fixed_mm', 'grip_length_loaded_mm'):
            for value in (-1, float('nan'), float('inf'), True, ''):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    normalise_options({key: value})

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

    def test_tetra_mode_preserves_surface_and_has_positive_tetrahedra(self):
        top = np.array([[.1, 1.8, .2], [.4, .7, 1.9]])
        before = top.copy()
        g = build_geometry(top, None, {
            'mesh_type': 'solid187_tetra', 'layers': 2, 'dx_mm': .025, 'dy_mm': .025})
        self.assertEqual(g['options']['mesh_type'], 'solid187_tetra')
        self.assertEqual(g['elements'].shape[1], 11)
        self.assertGreater(g['stats']['positive_tetra_count'], 0)
        self.assertEqual(g['stats']['negative_tetra_count'], 0)
        self.assertGreater(g['stats']['min_tetra_volume_mm3'], 0)
        np.testing.assert_array_equal(top, before)

    def test_unknown_mesh_type_is_rejected(self):
        with self.assertRaises(ValueError):
            normalise_options({'mesh_type': 'magic'})

    def test_solid285_mode_keeps_large_grid_with_four_node_tetrahedra(self):
        g = build_geometry(np.zeros((4, 5)), None, {
            'mesh_type': 'solid285_tetra', 'layers': 2, 'dx_mm': .025, 'dy_mm': .025})
        self.assertEqual(g['elements'].shape[1], 5)
        self.assertGreater(g['stats']['node_count'], 5 * 4 * 2)
        self.assertGreater(g['stats']['element_count'], 4 * 3 * 2)
        self.assertAlmostEqual(g['stats']['remaining_volume_mm3'], .1*.075*6)
        self.assertEqual(g['stats']['negative_tetra_count'], 0)

import copy
import math
import unittest

import numpy as np

from backend import apdl_diagnostics as diagnostics
from backend.apdl_geometry import build_geometry, normalise_options
from backend.apdl_presets import ORIGINAL_CURVE

def cube():
    xyz = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                    [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=float)
    return np.column_stack((np.arange(1, 9), xyz)), np.array([[1, 1, 2, 3, 4, 5, 6, 7, 8]])


class APDLDiagnosticsTests(unittest.TestCase):
    def test_output_defaults_and_each_save_mode(self):
        self.assertEqual(diagnostics.normalise_output_options({}), {
            'result_save_mode': 'all', 'field_output_times': [.25, .5, .75, 1.]})
        for mode, active in [('all', []), ('last', [1.]), ('selected', [.25, .5, .75, 1.])]:
            summary = diagnostics.output_policy_summary({'result_save_mode': mode})
            self.assertEqual(summary['result_save_mode'], mode)
            self.assertEqual(summary['active_field_output_times'], active)
            self.assertEqual(summary['curve_output'], 'all_substeps')
            self.assertEqual(summary['time_basis'], 'load_fraction')
        summary = diagnostics.output_policy_summary({'material_model': 'multilinear_iso'})
        self.assertEqual(summary['nldat_output'], 'all_substeps')

    def test_selected_rejects_invalid_or_injected_options(self):
        for times in ([], [.5], [0, 1], [-1, 1], [.5, .5, 1], [1, .5],
                      [1, 1.1], [True, 1], [float('nan'), 1], [float('inf'), 1],
                      ['.5', 1], '.5,1', {}, [[.5], 1], list(np.linspace(.01, 1, 21))):
            with self.subTest(times=times), self.assertRaises(ValueError):
                diagnostics.normalise_output_options({'result_save_mode': 'selected',
                                                       'field_output_times': times})
        for mode in ('ALL', '', '/EXIT', [], {}, True, None):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                diagnostics.normalise_output_options({'result_save_mode': mode})
        for options in (None, [], 'all'):
            with self.assertRaises(ValueError):
                diagnostics.normalise_output_options(options)

    def test_inactive_time_draft_is_copied_and_not_enabled(self):
        options = {'result_save_mode': 'last', 'field_output_times': [.7, .3]}
        before = copy.deepcopy(options)
        cleaned = diagnostics.normalise_output_options(options)
        self.assertEqual(cleaned['field_output_times'], [.7, .3])
        self.assertEqual(diagnostics.output_policy_summary(options)['active_field_output_times'], [1.])
        cleaned['field_output_times'].append(.9)
        self.assertEqual(options, before)

    def test_original_49_point_curve_coverage_uses_last_point_without_mutation(self):
        options = normalise_options({'material_model': 'multilinear_iso',
            'plastic_curve': copy.deepcopy(ORIGINAL_CURVE), 'allow_negative_slope': True,
            'E_MPa': 185226, 'length_mm': 57.6, 'target_displacement_mm': 11})
        before = copy.deepcopy(options)
        hint = diagnostics.material_coverage_hint(options)
        last_total = .137798 + 621.16 / 185226
        self.assertEqual(hint['status'], 'estimate_only')
        self.assertEqual(hint['last_plastic_strain'], .137798)
        self.assertEqual(hint['last_stress_MPa'], 621.16)
        self.assertAlmostEqual(hint['target_engineering_strain'], 11 / 57.6)
        self.assertAlmostEqual(hint['target_log_strain'], math.log1p(11 / 57.6))
        self.assertAlmostEqual(hint['estimated_last_total_strain'], last_total)
        self.assertAlmostEqual(hint['estimated_uniform_extension_mm'], 57.6 * math.expm1(last_total))
        self.assertTrue(hint['exceeds_estimated_coverage'])
        self.assertIn('积分点', ''.join(hint['warnings']))
        self.assertEqual(options, before)
        self.assertEqual(len(options['plastic_curve']), 49)

    def test_coverage_is_only_a_warning_and_small_displacement_is_not_acceptance(self):
        options = {'material_model': 'multilinear_iso', 'plastic_curve': [[0, 235], [.1, 300]],
                   'length_mm': 100, 'target_displacement_mm': .1, 'E_MPa': 200000}
        hint = diagnostics.material_coverage_hint(options)
        self.assertFalse(hint['exceeds_estimated_coverage'])
        self.assertIn('热点', ''.join(hint['warnings']))
        for model in ('elastic', 'bilinear_iso'):
            hint = diagnostics.material_coverage_hint({'material_model': model})
            self.assertEqual(hint['status'], 'not_applicable')
            self.assertIsNone(hint['last_plastic_strain'])
            self.assertIsNone(hint['exceeds_estimated_coverage'])

    def test_cube_has_unit_scaled_jacobian_and_preserves_arrays(self):
        nodes, elements = cube()
        before_nodes, before_elements = nodes.copy(), elements.copy()
        result = diagnostics.mesh_quality_precheck(nodes, elements)
        self.assertEqual(result['status'], 'precheck_only')
        self.assertAlmostEqual(result['min_scaled_jacobian'], 1.)
        self.assertAlmostEqual(result['max_edge_length_ratio'], 1.)
        self.assertEqual(result['warning_element_count'], 0)
        self.assertEqual(result['worst_elements'][0]['element_id'], 1)
        self.assertEqual(result['worst_elements'][0]['centroid_mm'], [.5, .5, .5])
        np.testing.assert_array_equal(nodes, before_nodes)
        np.testing.assert_array_equal(elements, before_elements)

    def test_extreme_shear_warns_and_reports_worst_element_location(self):
        nodes, elements = cube()
        nodes[4:, 1] += 100
        result = diagnostics.mesh_quality_precheck(nodes, elements)
        self.assertLess(result['min_scaled_jacobian'], .1)
        self.assertEqual(result['warning_element_count'], 1)
        self.assertGreater(result['max_edge_length_ratio'], 100)
        self.assertEqual(result['worst_elements'][0]['centroid_mm'], [50.5, .5, .5])
        self.assertIn('ANSYS', ''.join(result['warnings']))

    def test_inverted_corner_warns_without_repairing_mesh(self):
        nodes, elements = cube()
        nodes[:, 1] *= -1
        before = nodes.copy()
        result = diagnostics.mesh_quality_precheck(nodes, elements)
        self.assertAlmostEqual(result['min_scaled_jacobian'], -1.)
        self.assertEqual(result['warning_element_count'], 1)
        np.testing.assert_array_equal(nodes, before)

    def test_mesh_chunks_keep_global_statistics_and_limited_worst_ids(self):
        nodes, elements = cube()
        count = 20003
        elements = np.repeat(elements, count, axis=0)
        elements[:, 0] = np.arange(1, count + 1)
        result = diagnostics.mesh_quality_precheck(nodes, elements, limit=3)
        self.assertEqual(result['element_count'], count)
        self.assertEqual([item['element_id'] for item in result['worst_elements']], [1, 2, 3])
        self.assertEqual(result['min_scaled_jacobian'], 1.)

    def test_mesh_supports_explicit_noncontiguous_node_ids(self):
        nodes, elements = cube()
        nodes[:, 0] = np.arange(1, 9) * 10
        elements[:, 1:] *= 10
        result = diagnostics.mesh_quality_precheck(nodes[::-1], elements)
        self.assertEqual(result['min_scaled_jacobian'], 1.)

    def test_invalid_mesh_data_is_rejected_instead_of_reported_as_passed(self):
        nodes, elements = cube()
        bad_nodes = nodes.copy()
        bad_nodes[0, 1] = np.nan
        missing = elements.copy()
        missing[0, 1] = 999
        fractional = elements.astype(float)
        fractional[0, 1] = 1.5
        for ns, es in ((bad_nodes, elements), (nodes, missing), (nodes, fractional),
                       (nodes[:, :3], elements), (nodes, elements[:, :8])):
            with self.assertRaises(ValueError):
                diagnostics.mesh_quality_precheck(ns, es)

    def test_geometry_diagnostics_are_json_safe_and_read_only(self):
        import json
        geometry = build_geometry(None, None, {'corrosion_mode': 'flat', 'nx': 2, 'ny': 2, 'layers': 1})
        options = copy.deepcopy(geometry['options'])
        nodes = geometry['nodes'].copy()
        result = diagnostics.diagnostics_for_geometry(geometry)
        self.assertEqual(set(result), {'material_coverage', 'mesh_quality', 'output_policy'})
        json.dumps(result, allow_nan=False)
        self.assertEqual(geometry['options'], options)
        np.testing.assert_array_equal(geometry['nodes'], nodes)


if __name__ == '__main__':
    unittest.main()

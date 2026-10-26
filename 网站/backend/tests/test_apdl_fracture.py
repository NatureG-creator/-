import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from backend.apdl_geometry import build_geometry, normalise_options
from backend.apdl_deck import create_tension_bundle
from backend.apdl_fracture_results import load_path_exists, section_areas
from backend.apdl_presets import get_presets
from backend.apdl_outcome import explain_result


class FractureTests(unittest.TestCase):
    def options(self, **changes):
        values = next(p['options'] for p in get_presets() if p['id'] == 'gissmo_demo')
        return dict(values, **changes)

    def test_legacy_analysis_does_not_enable_damage(self):
        options = normalise_options({})
        self.assertEqual(options['damage_model'], 'none')
        self.assertFalse(options['large_deflection'])

    def test_invalid_physics_and_nonfinite_input_are_rejected(self):
        cases = [dict(material_model='elastic'), dict(large_deflection=False),
                 dict(mesh_type='solid187_tetra'), dict(boundary_mode='legacy_recommended'),
                 dict(density_tonne_mm3=True), dict(loading_time_s=float('nan')),
                 dict(damage_exponent=-1), dict(damage_damping_per_s=-1),
                 dict(damage_output_intervals=12), dict(damage_output_intervals=100.5),
                 dict(damage_failure_curve=[[0, .1], [1, .2]]),
                 dict(damage_size_curve=[[1, 1], [.5, 1]]),
                 dict(plastic_curve=[[0, 300], [.1, 250]], allow_negative_slope=True),
                 dict(neck_imperfection_fraction=.2), dict(damage_parameter_basis='unknown')]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                normalise_options(self.options(**changes))

    def test_measured_surface_is_never_modified_by_demo_imperfection(self):
        with self.assertRaisesRegex(ValueError, '初始缺陷'):
            build_geometry(np.zeros((5, 41)), None, self.options(corrosion_mode='single_top'))

    def test_demo_geometry_and_ascii_deck_preserve_physical_contract(self):
        geometry = build_geometry(None, None, self.options())
        self.assertAlmostEqual(geometry['remaining'].min(), .98)
        self.assertEqual(geometry['stats']['element_count'], 640)
        with tempfile.TemporaryDirectory() as temp:
            with patch('backend.apdl_deck._write_preview', side_effect=AssertionError('must not use MAPDL')):
                result = create_tension_bundle(geometry, Path(temp), {'test': 'only input generation'})
            deck = (Path(temp)/'tension.k').read_text(encoding='ascii')
            self.assertIn('*MAT_ADD_DAMAGE_GISSMO', deck)
            self.assertIn('*KEYWORD LONG=Y', deck)
            self.assertIn('*DAMPING_GLOBAL\n0,10000', deck)
            self.assertIn('0.0022,4', deck)  # Hold beyond the last explicit step; never snap displacement to zero.
            self.assertNotIn('EKILL', deck)
            self.assertNotIn('DT2MS', deck)
            self.assertFalse((Path(temp)/'force_displacement.csv').exists())
            with zipfile.ZipFile(Path(temp)/'lsdyna_fracture_input_bundle.zip') as archive:
                self.assertIn('manifest.json', archive.namelist())
            self.assertEqual(result['solver_type'], 'ls-dyna')

    def test_section_area_uses_native_deformed_geometry_in_both_axes(self):
        g = build_geometry(None, None, self.options(neck_imperfection_fraction=0))
        xyz = g['nodes'][:, 1:]
        np.testing.assert_allclose(section_areas(xyz, 41, 5, 4, 0), 2)
        np.testing.assert_allclose(section_areas(xyz, 41, 5, 4, 1), 10)
        contracted = xyz*np.array([1.2, .9, .8])
        np.testing.assert_allclose(section_areas(contracted, 41, 5, 4, 0), 2*.9*.8)

    def test_deleted_elements_do_not_imply_complete_fracture(self):
        g = build_geometry(None, None, self.options(neck_imperfection_fraction=0))
        connectivity = g['elements'][:, 1:]-1
        fixed = np.flatnonzero(g['nodes'][:, 1] == 0)
        loaded = np.flatnonzero(g['nodes'][:, 1] == 10)
        alive = np.ones(len(connectivity), dtype=bool)
        alive[0] = False
        self.assertTrue(load_path_exists(connectivity, alive, fixed, loaded, len(g['nodes'])))
        # Delete one entire section through width AND thickness.
        centers = g['nodes'][connectivity, 1].mean(axis=1)
        alive[centers == 5.125] = False
        self.assertFalse(load_path_exists(connectivity, alive, fixed, loaded, len(g['nodes'])))

    def test_ls_outcome_does_not_require_mapdl_static_logs(self):
        with tempfile.TemporaryDirectory() as temp:
            summary = dict(solver_type='ls-dyna', solve_state='solved',
                           results=dict(validation_state='native_binary_cross_checked'))
            report = explain_result(temp, summary, 'completed')
            self.assertTrue(report['loading_complete'])
            report = explain_result(temp, dict(summary, solve_state='failed'), 'failed')
            self.assertFalse(report['loading_complete'])

    def test_reader_uses_frozen_manifest_solver_when_options_are_omitted(self):
        from backend.apdl_solver import read_tension_results
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/'manifest.json').write_text(json.dumps({'options': self.options()}), encoding='utf-8')
            with patch('backend.apdl_fracture_results.read_fracture_results', return_value={'native': True}) as reader:
                self.assertEqual(read_tension_results(temp, {}), {'native': True})
                self.assertEqual(reader.call_args.args[2]['damage_model'], 'gissmo')


if __name__ == '__main__':
    unittest.main()

"""Synthetic diagnostic fixtures test software contracts, never MAPDL physics."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from backend.apdl_deck import create_tension_bundle
from backend.apdl_geometry import build_geometry
from backend.apdl_solver import read_tension_results


class APDLReportsTests(unittest.TestCase):
    def test_precheck_counts_must_follow_mesh_parameters(self):
        from backend.apdl_reports import _precheck
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            g, _, _ = self.fixture(out)
            g['stats']['element_count'] += 1
            path = out/'diagnostics_precheck.json'
            diagnostics = json.loads(path.read_text(encoding='utf-8'))
            diagnostics['mesh_quality']['element_count'] += 1
            path.write_text(json.dumps(diagnostics), encoding='utf-8')
            self.update_manifest(out, lambda m: m.update(
                stats=g['stats'], diagnostics=diagnostics,
                files={**m['files'], 'diagnostics_precheck.json':
                       hashlib.sha256(path.read_bytes()).hexdigest()}))
            with self.assertRaisesRegex(ValueError, '网格参数'):
                _precheck(out, g['stats'], g['options'])

    def test_solid187_en_emore_centroid_uses_four_corners(self):
        from backend.apdl_reports import _centroids
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out/'elements.dat').write_text('EN,1,1,2,3,4,5,6,7,8\nEMORE,9,10\n')
            xyz = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],
                [.5,0,0],[.5,.5,0],[0,.5,0],[0,0,.5],[.5,0,.5],[0,.5,.5]])
            nodes = np.column_stack((np.arange(1,11),xyz))
            np.testing.assert_allclose(_centroids(out,np.array([1]),nodes,1)[1], [.25,.25,.25])

    def fixture(self, out, *, material_model='multilinear_iso', last_plastic_strain=.1,
                tensile_direction='X'):
        g = build_geometry(None, None, dict(corrosion_mode='flat', nx=3, ny=2,
                           layers=2, material_model=material_model, export_full_field=False,
                           plastic_curve=[[0., 250.], [last_plastic_strain, 300.]],
                           tensile_direction=tensile_direction))
        with patch('backend.apdl_deck._write_preview', side_effect=lambda path, _: path.write_bytes(b'fixture')):
            create_tension_bundle(g, out, {})
        o, s = g['options'], g['stats']
        rows = []
        length = o['length_mm'] if tensile_direction == 'X' else o['width_mm']
        for time in (.5, 1.):
            u = time*o['target_displacement_mm']
            force = 100*time
            rows.append([time, u, force, -force, u/length, force/s['nominal_area_mm2']])
        np.savetxt(out/'force_displacement.csv', rows, delimiter=',')
        (out/'corrosion.rst').write_bytes(b'SYNTHETIC-CONTRACT-FIXTURE-NOT-MAPDL')
        selfcheck = [[1, s['node_count'], s['element_count'], -1, -1, 1],
                     [2, s['node_count'], s['element_count'],
                      (o['ny'] if tensile_direction == 'X' else o['nx'])*(o['layers']+1),
                      (o['ny'] if tensile_direction == 'X' else o['nx'])*(o['layers']+1), 1]]
        np.savetxt(out/'apdl_self_check.csv', selfcheck, delimiter=',')
        (out/'mesh_quality_report.txt').write_text('Synthetic raw ANSYS report fixture\nSHPP SUMMARY\n', encoding='utf-8')
        last = o['plastic_curve'][-1][0] if material_model == 'multilinear_iso' else .1
        centers = [g['nodes'][e[1:]-1, 1:].mean(axis=0) for e in g['elements']]
        history = np.asarray([[.5, last*.5, 1, *centers[0]], [1., last*1.1, 2, *centers[1]]])
        if material_model == 'multilinear_iso':
            np.savetxt(out/'material_coverage_history.csv', history, delimiter=',', fmt='%.11e')
        return g, np.asarray(selfcheck, dtype=float), history

    def read(self, out, g, **kwargs):
        with patch('backend.apdl_solver._write_curve_plot'):
            return read_tension_results(out, g['stats'], g['options'], **kwargs)

    def update_manifest(self, out, change):
        path = out/'manifest.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        change(manifest)
        path.write_text(json.dumps(manifest), encoding='utf-8')

    def test_actual_diagnostics_preserve_precheck_and_result_review_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); g, _, _ = self.fixture(out)
            result = self.read(out, g)
            d = result['diagnostics']
            self.assertEqual(d['self_check']['state'], 'passed')
            self.assertEqual(d['mesh_quality']['status'], 'precheck_only')
            self.assertEqual(d['mesh_quality']['native_report']['state'], 'needs_review')
            screening = d['material_coverage']['screening']
            self.assertEqual(screening['state'], 'flagged')
            self.assertEqual(screening['first_flag']['time'], 1.)
            self.assertEqual(screening['first_flag']['element_id'], 2)
            self.assertTrue(screening['centroid_verified'])
            self.assertIn('元素节点', screening['note'])
            self.assertIn('积分点', screening['note'])
            self.assertEqual(result['rst_validation']['state'], 'unverified')
            self.assertEqual(result['validation_state'], 'needs_review')
            for name in ('apdl_self_check.csv', 'mesh_quality_report.txt', 'material_coverage_history.csv', 'diagnostics_precheck.json'):
                self.assertIn(name, result['files'])
            self.assertTrue(any('超' in w and '元素节点' in w for w in result['warnings']))

    def test_y_tension_uses_y_axis_for_self_check_and_axial_length(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); g, _, _ = self.fixture(out, tensile_direction='Y')
            result = self.read(out, g)
            self.assertEqual(result['tensile_direction'], 'Y')
            self.assertEqual(result['axial_length_mm'], g['options']['width_mm'])
            self.assertEqual(result['diagnostics']['self_check']['state'], 'passed')
            self.assertEqual(result['diagnostics']['self_check']['stages'][1][3:5],
                             [g['options']['nx']*(g['options']['layers']+1)]*2)

    def test_missing_actual_file_fails_without_deleting_other_evidence(self):
        for name in ('apdl_self_check.csv', 'mesh_quality_report.txt', 'material_coverage_history.csv', 'diagnostics_precheck.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                out = Path(temp); g, _, _ = self.fixture(out)
                (out/name).unlink()
                with self.assertRaisesRegex(ValueError, name):
                    self.read(out, g)
                self.assertTrue((out/'force_displacement.csv').exists())

    def test_self_check_rows_counts_stages_pass_and_finite_columns_are_strict(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); g, valid, _ = self.fixture(out)
            corruptions = [valid[:1], valid[::-1], valid[:, :5], np.vstack((valid, valid[1]))]
            for row, col, value in ((0, 0, 1.5), (0, 1, 999), (1, 2, 0), (0, 3, 0),
                                    (1, 3, 4), (1, 4, 0), (1, 5, 0), (0, 5, np.nan), (1, 5, np.inf)):
                bad = valid.copy(); bad[row, col] = value; corruptions.append(bad)
            for bad in corruptions:
                with self.subTest(bad=bad.tolist()):
                    np.savetxt(out/'apdl_self_check.csv', bad, delimiter=',')
                    with self.assertRaisesRegex(ValueError, 'apdl_self_check'):
                        self.read(out, g)

    def test_history_rejects_bad_columns_nonfinite_negative_ids_times_and_centroids(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); g, _, valid = self.fixture(out)
            corruptions = [valid[:1], valid[:, :5], np.vstack((valid, valid[1]))]
            for row, col, value in ((1, 0, .5), (1, 0, .9), (1, 1, -1), (0, 1, np.nan),
                                    (1, 2, 0), (1, 2, 1.5), (1, 2, 999), (1, 3, np.inf), (1, 4, 999), (1, 5, -999)):
                bad = valid.copy(); bad[row, col] = value; corruptions.append(bad)
            for bad in corruptions:
                with self.subTest(bad=bad.tolist()):
                    np.savetxt(out/'material_coverage_history.csv', bad, delimiter=',')
                    with self.assertRaisesRegex(ValueError, 'material_coverage_history'):
                        self.read(out, g)

    def test_no_flag_is_only_an_element_nodal_proxy_not_integral_point_guarantee(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); g, _, history = self.fixture(out)
            history[:, 1] = 0
            np.savetxt(out/'material_coverage_history.csv', history, delimiter=',')
            screening = self.read(out, g)['diagnostics']['material_coverage']['screening']
            self.assertEqual(screening['state'], 'no_flag')
            self.assertIsNone(screening['first_flag'])
            self.assertIn('不能保证', screening['note'])

    def test_non_miso_has_no_history_requirement(self):
        for model in ('elastic', 'bilinear_iso'):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as temp:
                out = Path(temp); g, _, _ = self.fixture(out, material_model=model)
                self.assertEqual(self.read(out, g)['diagnostics']['material_coverage']['screening']['state'], 'not_applicable')

    def test_miso_limit_rounded_up_by_e19_11_export_is_a_review_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            last = .123456789127
            g, _, history = self.fixture(out, last_plastic_strain=last)
            history[:, 1] = [last*.5, last]
            # Unscaled APDL E19.11 has 11 significant digits (0.xxxxxxxxxxx).
            np.savetxt(out/'material_coverage_history.csv', history, delimiter=',', fmt='%.10e')
            screening = self.read(out, g)['diagnostics']['material_coverage']['screening']
            self.assertEqual(screening['max_element_nodal_epeq'], .12345678913)
            self.assertGreater(screening['max_element_nodal_epeq'], last)
            self.assertEqual(screening['state'], 'no_flag')
            self.assertIsNone(screening['first_flag'])
            self.assertEqual(screening.get('near_limit_point_count'), 1)
            self.assertEqual(screening.get('comparison_relative_tolerance'), 5.1e-11)
            self.assertIn('E19.11', screening['comparison_note'])
            self.assertIn('复核', screening['comparison_note'])
            self.assertIn('积分点', screening['note'])

    def test_miso_first_flag_skips_export_precision_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            last = .123456789127
            g, _, history = self.fixture(out, last_plastic_strain=last)
            history[:, 1] = [last, last*(1+1e-8)]
            np.savetxt(out/'material_coverage_history.csv', history, delimiter=',', fmt='%.10e')
            screening = self.read(out, g)['diagnostics']['material_coverage']['screening']
            self.assertEqual(screening['state'], 'flagged')
            self.assertEqual(screening['first_flag']['time'], 1.)
            self.assertEqual(screening['first_flag']['element_id'], 2)
            self.assertEqual(screening.get('near_limit_point_count'), 1)
            np.testing.assert_allclose(screening['first_flag']['centroid_mm'], history[1, 3:])

    def test_tiny_miso_limit_keeps_relative_exceedance_without_absolute_tolerance(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            last = 1e-16
            g, _, history = self.fixture(out, last_plastic_strain=last)
            history[:, 1] = [last*.5, last*1.1]
            np.savetxt(out/'material_coverage_history.csv', history, delimiter=',', fmt='%.10e')
            screening = self.read(out, g)['diagnostics']['material_coverage']['screening']
            self.assertEqual(screening['state'], 'flagged')
            self.assertEqual(screening.get('near_limit_point_count'), 0)
            self.assertEqual(screening['first_flag']['time'], 1.)
            self.assertEqual(screening['first_flag']['element_id'], 2)

    def test_empty_quality_report_does_not_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); g, _, _ = self.fixture(out)
            (out/'mesh_quality_report.txt').write_text(' \n\t', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'mesh_quality_report'):
                self.read(out, g)

    def test_unsupported_or_invalid_schema_never_downgrades_to_legacy(self):
        for version in (1, 3, 2., True, None, '2', {}, []):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temp:
                out = Path(temp); g, _, _ = self.fixture(out)
                self.update_manifest(out, lambda m: m.update(diagnostics_schema_version=version))
                with self.assertRaisesRegex(ValueError, 'schema'):
                    self.read(out, g)

    def test_legacy_without_schema_does_not_require_diagnostic_files(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); g, _, _ = self.fixture(out)
            self.update_manifest(out, lambda m: m.pop('diagnostics_schema_version'))
            for name in ('apdl_self_check.csv', 'mesh_quality_report.txt', 'material_coverage_history.csv', 'diagnostics_precheck.json'):
                (out/name).unlink()
            self.assertEqual(self.read(out, g)['solve_state'], 'solved')
            (out/'manifest.json').unlink()
            self.assertEqual(self.read(out, g)['solve_state'], 'solved')

    def test_manifest_precheck_hash_inputs_and_diagnostics_must_match(self):
        changes = [lambda m: m['files'].update({'diagnostics_precheck.json': 'bad'}),
                   lambda m: m['stats'].update(node_count=999),
                   lambda m: m['options'].update(target_displacement_mm=.2),
                   lambda m: m['diagnostics']['material_coverage'].update(last_plastic_strain=999),
                   lambda m: m['output_policy'].update(result_save_mode='last')]
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                out = Path(temp); g, _, _ = self.fixture(out)
                self.update_manifest(out, change)
                with self.assertRaisesRegex(ValueError, 'manifest|预检|一致|哈希'):
                    self.read(out, g)

    def test_same_history_element_can_recur_and_shuffled_expected_nodes_are_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); g, _, history = self.fixture(out)
            history[1, 2:] = history[0, 2:]
            np.savetxt(out/'material_coverage_history.csv', history, delimiter=',')
            result = self.read(out, g, expected_nodes=g['nodes'][::-1])
            self.assertEqual(result['diagnostics']['material_coverage']['screening']['first_flag']['element_id'], 1)

    def test_mesh_reference_corruption_does_not_claim_verified_centroids(self):
        for name in ('nodes.dat', 'elements.dat'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                out = Path(temp); g, _, _ = self.fixture(out)
                (out/name).write_text('broken mesh\n')
                with self.assertRaises(ValueError):
                    self.read(out, g)


if __name__ == '__main__':
    unittest.main()

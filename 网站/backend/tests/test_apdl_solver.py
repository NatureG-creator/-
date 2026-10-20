import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np

from backend.apdl_geometry import build_geometry
from backend.apdl_solver import mapdl_capabilities, read_tension_results, run_mapdl, _solver_errors


class APDLSolverTests(unittest.TestCase):
    def test_custom_self_check_and_native_quality_errors_are_recognised(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            (folder/'mapdl.out').write_text('APDL_SELF_CHECK_FAILED,BOUNDARY_COUNT\n')
            self.assertTrue(_solver_errors(folder))
            (folder/'mapdl.out').write_text('normal solver log\n')
            (folder/'mesh_quality_report.txt').write_text('*** ERROR *** invalid shape\n')
            self.assertTrue(_solver_errors(folder))
            (folder/'mesh_quality_report.txt').write_text('*** WARNING *** shape warning\n')
            self.assertFalse(_solver_errors(folder))
            (folder/'mapdl.out').write_text('/COM,APDL_SELF_CHECK_FAILED,MESH\n! APDL_SELF_CHECK_FAILED is only an input echo\n')
            self.assertFalse(_solver_errors(folder),'input command echoes are not executed failure markers')

    def test_old_diagnostics_are_never_reused_for_new_solver_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ('apdl_self_check.csv','mesh_quality_report.txt','material_coverage_history.csv'):
                path=Path(temp)/name
                path.write_text('previous output')
                with self.assertRaisesRegex(ValueError,'旧求解文件'):
                    run_mapdl(Path(temp),{})
                path.unlink()

    def fixture(self, folder, **options):
        setup = dict(corrosion_mode='flat', nx=2, ny=2, layers=1, export_full_field=False)
        setup.update(options)
        g = build_geometry(None, None, setup)
        o, s = g['options'], g['stats']
        rows = []
        axial_length = o['length_mm'] if o['tensile_direction'] == 'X' else o['width_mm']
        for time in (.5, 1):
            u = o['target_displacement_mm']*time
            force = s['analytic_stiffness_n_per_mm']*u
            rows.append([time, u, force, -force, u/axial_length, force/s['nominal_area_mm2']])
        np.savetxt(folder/'force_displacement.csv', rows, delimiter=',')
        (folder/'corrosion.rst').write_bytes(b'TEST-FIXTURE-ONLY-NOT-A-REAL-ANSYS-RESULT')
        return g, np.asarray(rows)

    def write_nodal_fixture(self, folder, geometry):
        """Synthetic field for CSV contract tests only; it is not ANSYS evidence."""
        nodes = geometry['nodes']
        o, s = geometry['options'], geometry['stats']
        axis_index = 1 if o['tensile_direction'] == 'X' else 2
        displacement_index = 0 if o['tensile_direction'] == 'X' else 1
        axial_length = o['length_mm'] if o['tensile_direction'] == 'X' else o['width_mm']
        axial_displacement = (nodes[:, axis_index]-nodes[:, axis_index].min())/axial_length*o['target_displacement_mm']
        displacements = np.zeros((len(nodes), 3))
        displacements[:, displacement_index] = axial_displacement
        nodal = np.column_stack((nodes, displacements,
                                 np.full(len(nodes), o['E_MPa']*o['target_displacement_mm']/axial_length),
                                 np.zeros(len(nodes))))
        np.savetxt(folder/'nodal_results.csv', nodal, delimiter=',', fmt='%.17g')
        return nodal

    def test_capabilities_only_checks_known_environment_and_install_locations(self):
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp)/'ansys242.exe'
            executable.write_bytes(b'fixture')
            with patch.dict('os.environ', {'MAPDL_BIN': str(executable)}, clear=True):
                value = mapdl_capabilities()
            self.assertTrue(value['available'])
            self.assertEqual(value['executable'], str(executable.resolve()))
            self.assertEqual(value['license_state'], 'unchecked')

    def test_missing_mapdl_is_unavailable_not_a_fake_solver_success(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output/'main.inp').write_text('/EXIT,NOSAVE')
            with patch('backend.apdl_solver.mapdl_capabilities', return_value={'available': False, 'executable': None, 'warnings': []}):
                with self.assertRaisesRegex(RuntimeError, 'MAPDL'):
                    run_mapdl(output, {'timeout_seconds': 1, 'cores': 2}, None)
            self.assertEqual(json.loads((output/'mapdl_execution.json').read_text(encoding='utf-8'))['state'], 'unavailable')

    def test_mock_batch_launch_and_error_log_are_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output/'main.inp').write_text('/EXIT,NOSAVE')
            process = Mock(pid=999999999)
            process.record = {'group_name': 'test-owned'}
            process.close.return_value = {'state': 'stopped', 'verified_empty': True}
            process.wait.return_value = 0
            cap = {'available': True, 'executable': r'C:\ANSYS\ansys242.exe', 'warnings': []}
            def launch(*args, **kwargs):
                (output/'mapdl.out').write_text('*** ERROR ***\nThe solution did not converge.')
                return process
            with patch('backend.apdl_solver.mapdl_capabilities', return_value=cap), patch('backend.apdl_solver.launch_owned', side_effect=launch) as popen:
                with self.assertRaisesRegex(RuntimeError, '错误|收敛'):
                    run_mapdl(output, {'timeout_seconds': 5, 'cores': 3}, None)
            args = popen.call_args.args[0]
            self.assertEqual(args[args.index('-np')+1], '3')
            self.assertEqual(args[args.index('-j')+1], 'corrosion')
            self.assertEqual(popen.call_args.args[1], output.resolve())
            self.assertEqual(json.loads((output/'mapdl_execution.json').read_text(encoding='utf-8'))['state'], 'failed')

    def test_mock_timeout_stops_only_the_started_process_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output/'main.inp').write_text('/EXIT,NOSAVE')
            process = Mock(pid=999999999)
            process.record = {'group_name': 'test-owned'}
            process.close.return_value = {'state': 'stopped', 'verified_empty': True}
            process.wait.side_effect = [subprocess.TimeoutExpired('ansys', 1), 0]
            cap = {'available': True, 'executable': 'ansys242.exe', 'warnings': []}
            with patch('backend.apdl_solver.mapdl_capabilities', return_value=cap), patch('backend.apdl_solver.launch_owned', return_value=process), patch('backend.apdl_solver._stop_process_tree', return_value={'state': 'stopped', 'verified_empty': True}) as stop:
                with self.assertRaisesRegex(RuntimeError, '超时'):
                    run_mapdl(output, {'timeout_seconds': 1, 'cores': 2}, None)
            stop.assert_called_once_with(process)
            self.assertEqual(json.loads((output/'mapdl_execution.json').read_text(encoding='utf-8'))['state'], 'timeout')

    def test_fixture_result_contract_and_analytic_error(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, rows = self.fixture(out)
            result = read_tension_results(out, g['stats'], g['options'])
            self.assertEqual(result['solve_state'], 'solved')
            self.assertEqual(result['point_count'], 2)
            self.assertAlmostEqual(result['analytic_reference']['stiffness_relative_error'], 0)
            self.assertAlmostEqual(result['final_load_n'], rows[-1, 2])
            self.assertTrue((out/'load_displacement.png').is_file())

    def test_y_tension_result_uses_y_length_and_validates_uy_on_y_grips(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, rows = self.fixture(out, length_mm=12, width_mm=6, nx=3, ny=2,
                                   tensile_direction='Y')
            self.write_nodal_fixture(out, g)
            result = read_tension_results(out, g['stats'], g['options'], expected_nodes=g['nodes'])
            self.assertEqual(result['tensile_direction'], 'Y')
            self.assertEqual(result['axial_length_mm'], 6)
            self.assertAlmostEqual(rows[-1, 4], rows[-1, 1]/6)
            self.assertAlmostEqual(rows[-1, 5], rows[-1, 2]/72)
            self.assertTrue(result['checks']['nodal_displacements'])
            self.assertAlmostEqual(result['analytic_reference']['stiffness_n_per_mm'], 206000*72/6)

    def test_truncated_unbalanced_inconsistent_or_nonfinite_curve_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, rows = self.fixture(out)
            corruptions = []
            v = rows.copy(); v[-1, 0] = .9; corruptions.append(v)
            v = rows.copy(); v[-1, 1] *= .9; corruptions.append(v)
            v = rows.copy(); v[-1, 3] = 0; corruptions.append(v)
            v = rows.copy(); v[-1, 4] *= 2; corruptions.append(v)
            v = rows.copy(); v[-1, 5] *= 2; corruptions.append(v)
            v = rows.copy(); v[-1, 2] = np.nan; corruptions.append(v)
            corruptions.append(rows[:, :5])
            for array in corruptions:
                np.savetxt(out/'force_displacement.csv', array, delimiter=',')
                with self.subTest(array=array), self.assertRaises(ValueError):
                    read_tension_results(out, g['stats'], g['options'])

    def test_rst_and_optional_nodal_contract_required(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, _ = self.fixture(out)
            (out/'corrosion.rst').write_bytes(b'')
            with self.assertRaisesRegex(ValueError, 'RST|rst'):
                read_tension_results(out, g['stats'], g['options'])
            (out/'corrosion.rst').write_bytes(b'fixture')
            nodal = self.write_nodal_fixture(out, g)
            result = read_tension_results(out, g['stats'], g['options'], expected_nodes=g['nodes'])
            self.assertEqual(result['nodal_summary']['node_count'], len(g['nodes']))
            nodal[-1, 0] = nodal[0, 0]
            np.savetxt(out/'nodal_results.csv', nodal, delimiter=',')
            with self.assertRaisesRegex(ValueError, '节点'):
                read_tension_results(out, g['stats'], g['options'], expected_nodes=g['nodes'])

    def test_nonempty_fixture_rst_remains_unverified(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, _ = self.fixture(out)
            result = read_tension_results(out, g['stats'], g['options'])
            self.assertEqual(result['rst_validation']['state'], 'unverified')
            self.assertTrue(result['rst_validation']['reason'])
            self.assertIsNone(result['checks']['rst_consistency'])
            self.assertEqual(result['validation_state'], 'needs_review')

    def test_nodal_coordinates_are_matched_by_id_with_export_precision(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, _ = self.fixture(out, nx=4, length_mm=12.345678, origin_x_mm=100.123456)
            nodal = self.write_nodal_fixture(out, g)
            # Row ordering is immaterial; the model's node identifiers are authoritative.
            np.savetxt(out/'nodal_results.csv', nodal[::-1], delimiter=',', fmt='%.17g')
            result = read_tension_results(out, g['stats'], g['options'], expected_nodes=g['nodes'])
            self.assertTrue(result['checks']['nodal_coordinates'])
            self.assertTrue(result['checks']['nodal_displacements'])
            nodal[0, 1] = 12345
            np.savetxt(out/'nodal_results.csv', nodal, delimiter=',')
            with self.assertRaisesRegex(ValueError, '坐标'):
                read_tension_results(out, g['stats'], g['options'], expected_nodes=g['nodes'])

    def test_fortran_e13_5_five_significant_digit_rounding_is_accepted(self):
        # Without 1P, Fortran E13.5 uses 0.xxxxxE+nn (five significant digits).
        # These are literal CSV contract fixtures, not output from real MAPDL.
        scenarios = [
            ({'length_mm': 12.345678, 'origin_x_mm': 100.123456},
             ('0.10012E+03', '0.11247E+03'), '0.10000E+00'),
            ({'target_displacement_mm': .100123456},
             ('0.00000E+00', '0.10000E+03'), '0.10012E+00'),
        ]
        for options, x, ux in scenarios:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temp:
                out = Path(temp)
                g, _ = self.fixture(out, **options)
                lines = []
                for index, (_, _, y, z) in enumerate(g['nodes']):
                    # Y/Z only take the exact literal values 0, 20 and 6.
                    yy = '0.00000E+00' if y == 0 else '0.20000E+02'
                    zz = '0.00000E+00' if z == 0 else '0.60000E+01'
                    uu = '0.00000E+00' if index % 2 == 0 else ux
                    lines.append(f'{index+1},{x[index % 2]},{yy},{zz},{uu},0.00000E+00,0.00000E+00,0.10000E+03,0.00000E+00')
                csv = '\n'.join(lines)+'\n'
                (out/'nodal_results.csv').write_text(csv, encoding='ascii')
                result = read_tension_results(out, g['stats'], g['options'], expected_nodes=g['nodes'])
                self.assertTrue(result['checks']['nodal_coordinates'])
                self.assertTrue(result['checks']['nodal_displacements'])
                # A change larger than five-digit rounding must remain rejected.
                for before, after, reason in ((x[1], '0.11249E+03' if options.get('origin_x_mm') else '0.10002E+03', '坐标'),
                                               (ux, '0.10014E+00', '位移')):
                    (out/'nodal_results.csv').write_text(csv.replace(before, after), encoding='ascii')
                    with self.assertRaisesRegex(ValueError, reason):
                        read_tension_results(out, g['stats'], g['options'], expected_nodes=g['nodes'])

    def test_zero_or_wrong_grip_displacements_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, _ = self.fixture(out, nx=3)
            nodal = self.write_nodal_fixture(out, g)
            for label in ('all_zero', 'wrong_loaded', 'wrong_fixed'):
                damaged = nodal.copy()
                if label == 'all_zero':
                    damaged[:, 4] = 0
                elif label == 'wrong_loaded':
                    damaged[np.argmax(damaged[:, 1]), 4] *= .5
                else:
                    damaged[np.argmin(damaged[:, 1]), 4] = .01
                np.savetxt(out/'nodal_results.csv', damaged, delimiter=',')
                with self.subTest(label=label), self.assertRaisesRegex(ValueError, '位移|加载端|固定端'):
                    read_tension_results(out, g['stats'], g['options'], expected_nodes=g['nodes'])

    def test_nodes_dat_uses_actual_apdl_command_format_for_recovery(self):
        from backend.apdl_deck import create_tension_bundle
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, _ = self.fixture(out)
            create_tension_bundle(g, out, {})
            self.write_nodal_fixture(out, g)
            # Synthetic software-contract fixture; this is not MAPDL evidence.
            s, o = g['stats'], g['options']
            grip = o['ny']*(o['layers']+1)
            np.savetxt(out/'apdl_self_check.csv',
                       [[1, s['node_count'], s['element_count'], -1, -1, 1],
                        [2, s['node_count'], s['element_count'], grip, grip, 1]], delimiter=',')
            (out/'mesh_quality_report.txt').write_text('Synthetic CHECK/SHPP report fixture\n')
            self.assertTrue((out/'nodes.dat').read_text().startswith('N,1,'))
            result = read_tension_results(out, g['stats'], g['options'])
            self.assertTrue(result['checks']['nodal_coordinates'])
            self.assertTrue(result['checks']['nodal_displacements'])

    def test_missing_or_invalid_mesh_reference_is_explicitly_unverified(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, _ = self.fixture(out)
            self.write_nodal_fixture(out, g)
            for content in (None, '1,0,0,0\n'):
                if content is not None:
                    (out/'nodes.dat').write_text(content)
                result = read_tension_results(out, g['stats'], g['options'])
                self.assertIsNone(result['checks']['nodal_coordinates'])
                self.assertIsNone(result['checks']['nodal_displacements'])
                self.assertEqual(result['validation_state'], 'needs_review')
                self.assertTrue(any('网格' in warning for warning in result['warnings']))

    def test_zero_response_without_analytic_reference_is_flagged(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, rows = self.fixture(out, boundary_mode='clamped_grips')
            rows[:, 2:4] = 0
            rows[:, 5] = 0
            np.savetxt(out/'force_displacement.csv', rows, delimiter=',')
            result = read_tension_results(out, g['stats'], g['options'])
            self.assertFalse(result['checks']['nonzero_response'])
            self.assertEqual(result['validation_state'], 'needs_review')
            self.assertTrue(any('承载' in warning or '反力' in warning for warning in result['warnings']))

    def test_balanced_negative_reactions_do_not_assume_solver_sign_convention(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, rows = self.fixture(out)
            rows[:, 2:4] *= -1
            rows[:, 5] *= -1
            np.savetxt(out/'force_displacement.csv', rows, delimiter=',')
            result = read_tension_results(out, g['stats'], g['options'])
            self.assertTrue(result['checks']['nonzero_response'])
            self.assertTrue(result['checks']['analytic_reference'])
            self.assertLess(result['final_load_n'], 0)

    def test_significant_reaction_reversal_without_reference_is_flagged(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, rows = self.fixture(out, boundary_mode='clamped_grips')
            rows[0, 2:4] *= -1
            rows[0, 5] *= -1
            np.savetxt(out/'force_displacement.csv', rows, delimiter=',')
            result = read_tension_results(out, g['stats'], g['options'])
            self.assertFalse(result['checks']['nonzero_response'])
            self.assertTrue(any('符号反转' in warning for warning in result['warnings']))

    def test_plot_failure_keeps_result_data_and_does_not_fake_analytic_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, _ = self.fixture(out, boundary_mode='clamped_grips')
            with patch('backend.apdl_solver._write_curve_plot', side_effect=RuntimeError('plot failed')):
                result = read_tension_results(out, g['stats'], g['options'])
            self.assertEqual(result['solve_state'], 'solved')
            self.assertIsNone(result['analytic_reference'])
            self.assertTrue(result['warnings'])

    def test_requested_nodal_field_is_required_and_manifest_options_can_be_used(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, _ = self.fixture(out, export_full_field=True)
            (out/'manifest.json').write_text(json.dumps({'options': g['options']}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '节点|nodal'):
                read_tension_results(out, g['stats'])

    def test_existing_outputs_rejected_without_overwriting_old_execution_record(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out/'main.inp').write_text('/EXIT,NOSAVE')
            (out/'mapdl_execution.json').write_text('old evidence')
            with patch('backend.apdl_solver.subprocess.Popen') as launch:
                with self.assertRaisesRegex(ValueError, '已有|旧|新任务'):
                    run_mapdl(out, {}, None)
            launch.assert_not_called()
            self.assertEqual((out/'mapdl_execution.json').read_text(), 'old evidence')

    def test_every_curve_point_must_follow_ramped_displacement_and_analytic_check_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            g, rows = self.fixture(out)
            rows[0, 1] *= .5
            rows[0, 4] = rows[0, 1]/g['stats']['length_mm']
            np.savetxt(out/'force_displacement.csv', rows, delimiter=',')
            with self.assertRaisesRegex(ValueError, '加载|位移'):
                read_tension_results(out, g['stats'], g['options'])
            g, rows = self.fixture(out)
            rows[:, 2:4] *= .5
            rows[:, 5] *= .5
            np.savetxt(out/'force_displacement.csv', rows, delimiter=',')
            result = read_tension_results(out, g['stats'], g['options'])
            self.assertFalse(result['checks']['analytic_reference'])
            self.assertEqual(result['validation_state'], 'needs_review')

    def test_cleanup_failure_preserves_original_solver_error(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output/'main.inp').write_text('/EXIT,NOSAVE')
            process = Mock(pid=999999999)
            process.record = {'group_name': 'test-owned'}
            process.wait.side_effect = subprocess.TimeoutExpired('ansys', 1)
            process.close.return_value = {'state': 'failed', 'verified_empty': False, 'error': 'denied'}
            cap = {'available': True, 'executable': 'ansys.exe', 'warnings': []}
            with patch('backend.apdl_solver.mapdl_capabilities', return_value=cap), patch('backend.apdl_solver.launch_owned', return_value=process):
                with self.assertRaisesRegex(RuntimeError, '超时'):
                    run_mapdl(output, {'timeout_seconds': 1})
            record = json.loads((output/'mapdl_execution.json').read_text(encoding='utf-8'))
            self.assertEqual(record['state'], 'timeout')
            self.assertEqual(record['cleanup']['state'], 'failed')
            self.assertIn('超时', record['error'])

    def test_normal_exit_with_cleanup_failure_cannot_report_process_finished(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output/'main.inp').write_text('/EXIT,NOSAVE')
            process = Mock(pid=999999999)
            process.record = {'group_name': 'test-owned'}
            process.wait.return_value = 0
            process.close.return_value = {'state': 'failed', 'verified_empty': False, 'error': 'denied'}
            cap = {'available': True, 'executable': 'ansys.exe', 'warnings': []}
            def launch(*args):
                (output/'mapdl.out').write_text('normal process fixture')
                return process
            with patch('backend.apdl_solver.mapdl_capabilities', return_value=cap), patch('backend.apdl_solver.launch_owned', side_effect=launch):
                with self.assertRaisesRegex(RuntimeError, '清理'):
                    run_mapdl(output, {'timeout_seconds': 1})
            record = json.loads((output/'mapdl_execution.json').read_text(encoding='utf-8'))
            self.assertEqual(record['state'], 'failed')
            self.assertFalse(record['cleanup']['verified_empty'])

    def test_final_persistence_failure_keeps_solver_and_cleanup_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output/'main.inp').write_text('/EXIT,NOSAVE')
            process = Mock(pid=999999999)
            process.record = {'group_name': 'test-owned'}
            process.wait.side_effect = RuntimeError('solver original failure')
            process.close.return_value = {'state': 'failed', 'verified_empty': False, 'error': 'cleanup denied'}
            cap = {'available': True, 'executable': 'ansys.exe', 'warnings': []}
            original_write = Path.write_text
            writes = []
            def write(path, text, *args, **kwargs):
                if path.name == 'mapdl_execution.json.tmp':
                    writes.append(text)
                    if len(writes) > 1:
                        raise PermissionError('execution disk denied')
                return original_write(path, text, *args, **kwargs)
            with patch('backend.apdl_solver.mapdl_capabilities', return_value=cap), patch('backend.apdl_solver.launch_owned', return_value=process), patch.object(Path, 'write_text', write):
                with self.assertRaisesRegex(RuntimeError, 'solver original failure') as caught:
                    run_mapdl(output, {'timeout_seconds': 1})
            notes = '\n'.join(getattr(caught.exception, '__notes__', []))
            self.assertIn('cleanup denied', notes)
            self.assertIn('execution disk denied', notes)
            self.assertEqual(len(writes), 2)
            # Only the earlier running record exists; never claim final state persisted.
            stored = json.loads((output/'mapdl_execution.json').read_text(encoding='utf-8'))
            self.assertEqual(stored['state'], 'running')

    def test_final_persistence_failure_without_primary_error_raises(self):
        for cleanup_failed in (False, True):
            with self.subTest(cleanup_failed=cleanup_failed), tempfile.TemporaryDirectory() as temp:
                output = Path(temp)
                (output/'main.inp').write_text('/EXIT,NOSAVE')
                process = Mock(pid=999999999)
                process.record = {'group_name': 'test-owned'}
                process.wait.return_value = 0
                process.close.return_value = ({'state': 'failed', 'verified_empty': False, 'error': 'cleanup denied'}
                                              if cleanup_failed else {'state': 'stopped', 'verified_empty': True})
                cap = {'available': True, 'executable': 'ansys.exe', 'warnings': []}
                original_write = Path.write_text
                writes = []
                def write(path, text, *args, **kwargs):
                    if path.name == 'mapdl_execution.json.tmp':
                        writes.append(text)
                        if len(writes) > 1:
                            raise PermissionError('execution disk denied')
                    return original_write(path, text, *args, **kwargs)
                def launch(*args):
                    (output/'mapdl.out').write_text('normal process fixture')
                    return process
                with patch('backend.apdl_solver.mapdl_capabilities', return_value=cap), patch('backend.apdl_solver.launch_owned', side_effect=launch), patch.object(Path, 'write_text', write):
                    if cleanup_failed:
                        with self.assertRaisesRegex(RuntimeError, 'cleanup denied') as caught:
                            run_mapdl(output, {'timeout_seconds': 1})
                        self.assertIn('execution disk denied', '\n'.join(caught.exception.__notes__))
                    else:
                        with self.assertRaisesRegex(PermissionError, 'execution disk denied') as caught:
                            run_mapdl(output, {'timeout_seconds': 1})
                        self.assertIn('未持久化', '\n'.join(caught.exception.__notes__))

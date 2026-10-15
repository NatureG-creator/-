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
from backend.apdl_solver import mapdl_capabilities, read_tension_results, run_mapdl


class APDLSolverTests(unittest.TestCase):
    def fixture(self, folder, **options):
        setup = dict(corrosion_mode='flat', nx=2, ny=2, layers=1, export_full_field=False)
        setup.update(options)
        g = build_geometry(None, None, setup)
        o, s = g['options'], g['stats']
        rows = []
        for time in (.5, 1):
            u = o['target_displacement_mm']*time
            force = s['analytic_stiffness_n_per_mm']*u
            rows.append([time, u, force, -force, u/s['length_mm'], force/s['nominal_area_mm2']])
        np.savetxt(folder/'force_displacement.csv', rows, delimiter=',')
        (folder/'corrosion.rst').write_bytes(b'TEST-FIXTURE-ONLY-NOT-A-REAL-ANSYS-RESULT')
        return g, np.asarray(rows)

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
            process.wait.return_value = 0
            cap = {'available': True, 'executable': r'C:\ANSYS\ansys242.exe', 'warnings': []}
            def launch(*args, **kwargs):
                (output/'mapdl.out').write_text('*** ERROR ***\nThe solution did not converge.')
                return process
            with patch('backend.apdl_solver.mapdl_capabilities', return_value=cap), patch('backend.apdl_solver.subprocess.Popen', side_effect=launch) as popen:
                with self.assertRaisesRegex(RuntimeError, '错误|收敛'):
                    run_mapdl(output, {'timeout_seconds': 5, 'cores': 3}, None)
            args = popen.call_args.args[0]
            self.assertEqual(args[args.index('-np')+1], '3')
            self.assertEqual(args[args.index('-j')+1], 'corrosion')
            self.assertEqual(popen.call_args.kwargs['cwd'], str(output.resolve()))
            self.assertEqual(json.loads((output/'mapdl_execution.json').read_text(encoding='utf-8'))['state'], 'failed')

    def test_mock_timeout_stops_only_the_started_process_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output/'main.inp').write_text('/EXIT,NOSAVE')
            process = Mock(pid=999999999)
            process.wait.side_effect = [subprocess.TimeoutExpired('ansys', 1), 0]
            cap = {'available': True, 'executable': 'ansys242.exe', 'warnings': []}
            with patch('backend.apdl_solver.mapdl_capabilities', return_value=cap), patch('backend.apdl_solver.subprocess.Popen', return_value=process), patch('backend.apdl_solver._stop_process_tree') as stop:
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
            nodal = np.column_stack((g['nodes'], np.zeros((len(g['nodes']), 5))))
            np.savetxt(out/'nodal_results.csv', nodal, delimiter=',')
            result = read_tension_results(out, g['stats'], g['options'])
            self.assertEqual(result['nodal_summary']['node_count'], len(g['nodes']))
            nodal[-1, 0] = nodal[0, 0]
            np.savetxt(out/'nodal_results.csv', nodal, delimiter=',')
            with self.assertRaisesRegex(ValueError, '节点'):
                read_tension_results(out, g['stats'], g['options'])

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

    def test_real_owned_python_parent_and_child_are_stopped(self):
        import psutil
        from backend.apdl_solver import _stop_process_tree
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'child_pid.txt'
            code = "import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)']); Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(90)"
            process = subprocess.Popen([sys.executable, '-c', code, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic()+10
                while not path.exists() and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue(path.exists(), 'owned test parent must start its own child')
                child_pid = int(path.read_text())
                _stop_process_tree(process)
                self.assertIsNotNone(process.poll())
                self.assertFalse(psutil.pid_exists(child_pid))
            finally:
                _stop_process_tree(process)

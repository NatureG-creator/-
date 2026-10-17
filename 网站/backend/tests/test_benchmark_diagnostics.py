import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

class DiagnosticsTests(unittest.TestCase):
    def test_gpu_cpu_fallback_is_unavailable(self):
        from backend.benchmark_diagnostics import normalize_probe
        result = normalize_probe('gpu', {'state':'passed', 'actual_arch':'x64', 'message':'ok'}, 0.1)
        self.assertEqual(result['state'], 'unavailable')

    def test_report_persists_each_check_and_metadata_without_importing_taichi(self):
        from backend.benchmark_diagnostics import run_diagnostics
        with tempfile.TemporaryDirectory() as directory:
            with patch('backend.benchmark_diagnostics._run_probe', side_effect=lambda name, out, timeout: {'name':name,'state':'failed','message':'DLL load failed','elapsed_seconds':0.01}), patch('backend.benchmark_diagnostics.inspect_native_dependencies', return_value={'status':'unknown','missing':[]}):
                result = run_diagnostics(Path(directory))
            self.assertEqual([c['name'] for c in result['checks']], ['import','cpu','gpu'])
            self.assertGreater(result['hardware']['logical_cpu_count'], 0)
            self.assertTrue(result['python']['executable'])
            self.assertEqual(json.loads((Path(directory)/'diagnostics.json').read_text(encoding='utf-8'))['kind'], 'diagnostics')

if __name__ == '__main__':
    unittest.main()

class ProbeTimeoutTests(unittest.TestCase):
    def test_timeout_terminates_process_tree_and_logs(self):
        import subprocess
        from backend.benchmark_diagnostics import _run_probe
        process = unittest.mock.MagicMock()
        process.pid = 12345
        process.wait.side_effect = [subprocess.TimeoutExpired('probe', 0.1), 0]
        process.poll.return_value = 0
        with tempfile.TemporaryDirectory() as directory:
            with patch('backend.benchmark_diagnostics.subprocess.Popen', return_value=process), patch('backend.benchmark_diagnostics.subprocess.run') as kill:
                result = _run_probe('cpu', Path(directory), 0.1)
            self.assertEqual(result['state'], 'timeout')
            self.assertIn('超时', (Path(directory)/'cpu.log').read_text(encoding='utf-8'))
            import os
            if os.name == 'nt':
                self.assertEqual(kill.call_args.args[0], ['taskkill','/PID','12345','/T','/F'])

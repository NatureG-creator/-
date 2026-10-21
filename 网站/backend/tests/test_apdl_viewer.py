"""Interactive viewer contracts; mocked launches do not prove GUI readiness."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import urllib.request

from backend import apdl_viewer


class ViewerTests(unittest.TestCase):
    def fixture(self, temp):
        service = Mock(runtime=Path(temp))
        service.validate_id.side_effect = lambda value: value if value == '0123456789abcdef' else (_ for _ in ()).throw(ValueError('ID'))
        service.get_job.return_value = dict(id='0123456789abcdef', kind='apdl_tension', state='completed',
            summary={'options': {'material_model': 'multilinear_iso'}, 'solve_state': 'solved'})
        output = Path(temp)/'jobs/0123456789abcdef/outputs'
        output.mkdir(parents=True)
        for name in ('corrosion.db', 'corrosion.rst'):
            (output/name).write_bytes(b'fixture')
        return service, output

    def test_options_require_database_and_only_offer_available_results(self):
        with tempfile.TemporaryDirectory() as temp:
            service, output = self.fixture(temp)
            views = apdl_viewer.viewer_source(service, '0123456789abcdef')[0]['views']
            self.assertIn('plastic_strain', [v['id'] for v in views])
            service.get_job.return_value['summary']['options']['material_model'] = 'elastic'
            self.assertNotIn('plastic_strain', [v['id'] for v in apdl_viewer.viewer_source(service, '0123456789abcdef')[0]['views']])
            (output/'corrosion.rst').unlink()
            self.assertEqual([v['id'] for v in apdl_viewer.viewer_source(service, '0123456789abcdef')[0]['views']], ['model', 'mesh'])
            (output/'corrosion.db').unlink()
            with self.assertRaises(ValueError):
                apdl_viewer.viewer_source(service, '0123456789abcdef')

    def test_running_and_foreign_jobs_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            service, _ = self.fixture(temp)
            for key, value in [('state', 'running'), ('kind', 'simulation')]:
                original = service.get_job.return_value[key]
                service.get_job.return_value[key] = value
                with self.assertRaises(ValueError):
                    apdl_viewer.viewer_source(service, '0123456789abcdef')
                service.get_job.return_value[key] = original

    def test_launch_is_interactive_isolated_and_never_solves_or_saves(self):
        with tempfile.TemporaryDirectory() as temp:
            service, output = self.fixture(temp)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            process = Mock(pid=1234)
            process.poll.return_value = None
            with patch.object(apdl_viewer, 'mapdl_capabilities', return_value={'available': True, 'executable': 'ansys252.exe'}), patch.object(apdl_viewer.subprocess, 'Popen', return_value=process) as launch:
                result = apdl_viewer.open_viewer(service, '0123456789abcdef', {'view': 'stress'})
            command = launch.call_args.args[0]
            self.assertIn('-g', command)
            self.assertIn('-s', command)
            self.assertEqual(command[command.index('-s') + 1], 'read')
            self.assertNotIn('-b', command)
            session = Path(result['session_directory'])
            self.assertEqual((session/'start.ans').read_text(encoding=apdl_viewer._apdl_text_encoding()), '/INPUT,viewer,inp\n')
            startup = (session/'viewer.inp').read_text()
            macro = startup+'\n'+'\n'.join(p.read_text() for p in session.glob('*.mac'))
            self.assertIn('PLNSOL,S,EQV', macro)
            self.assertIn('SET,LAST', macro)
            self.assertIn('/PLOPTS,LEG1,1', macro)
            self.assertIn('../../jobs/0123456789abcdef/outputs/corrosion', startup)
            self.assertIn('/CLEAR,NOSTART', macro)
            self.assertNotIn('/CLEAR,START', macro)
            self.assertNotIn('/MREP', startup)
            self.assertIn("*ABBR,STRESS,'/INPUT,v_stress,mac'", startup)
            self.assertIn('/EDGE,1,0', (session/'v_mesh.mac').read_text())
            self.assertIn('/EDGE,1,1', (session/'v_model.mac').read_text())
            for line in macro.splitlines():
                self.assertNotIn(line.split(',')[0].upper(), ['SOLVE', 'SAVE', '/SOLU', 'UPGEOM', '/EXIT'])
            self.assertEqual(json.loads((session/'session.json').read_text(encoding='utf-8'))['pid'], 1234)
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_unicode_runtime_path_writes_complete_result_macros(self):
        with tempfile.TemporaryDirectory(prefix='中文运行目录') as temp:
            service, output = self.fixture(temp)
            process = Mock(pid=1235)
            process.poll.return_value = None
            with patch.object(apdl_viewer, 'mapdl_capabilities', return_value={'available': True, 'executable': 'ansys252.exe'}), patch.object(apdl_viewer.subprocess, 'Popen', return_value=process):
                result = apdl_viewer.open_viewer(service, '0123456789abcdef', {'view': 'plastic_strain'})
            session = Path(result['session_directory'])
            self.assertIn('PLNSOL,U,SUM', (session/'v_displacement.mac').read_text(encoding=apdl_viewer._apdl_text_encoding()))
            self.assertIn('PLNSOL,EPPL,EQV', (session/'v_plastic_strain.mac').read_text(encoding=apdl_viewer._apdl_text_encoding()))
            self.assertIn('../../jobs/0123456789abcdef/outputs/corrosion', (session/'viewer.inp').read_text(encoding=apdl_viewer._apdl_text_encoding()))

    def test_unavailable_or_invalid_view_never_launches(self):
        with tempfile.TemporaryDirectory() as temp:
            service, output = self.fixture(temp)
            with patch.object(apdl_viewer.subprocess, 'Popen') as launch:
                with self.assertRaises(ValueError):
                    apdl_viewer.open_viewer(service, '0123456789abcdef', {'view': '/SOLU'})
                (output/'corrosion.rst').unlink()
                with self.assertRaises(ValueError):
                    apdl_viewer.open_viewer(service, '0123456789abcdef', {'view': 'stress'})
                launch.assert_not_called()

    def test_symlink_outside_job_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            service, output = self.fixture(temp)
            outside = Path(temp)/'outside.db'
            outside.write_bytes(b'outside')
            with patch.object(Path, 'resolve', autospec=True, side_effect=lambda p: outside if p.name == 'corrosion.db' else p.absolute()):
                with self.assertRaises(ValueError):
                    apdl_viewer.viewer_source(service, '0123456789abcdef')

    def test_http_routes_pass_only_selected_task_and_view(self):
        from backend.server import make_server
        with tempfile.TemporaryDirectory() as temp:
            server = make_server(port=0, runtime=Path(temp))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                with patch.object(apdl_viewer, 'viewer_jobs', return_value={'available': True, 'jobs': []}):
                    with urllib.request.urlopen(base+'/api/apdl/viewer/jobs') as response:
                        self.assertEqual(json.load(response)['jobs'], [])
                with patch.object(apdl_viewer, 'open_viewer', return_value={'state': 'launch_requested', 'pid': 1234}) as opened:
                    request = urllib.request.Request(base+'/api/apdl/jobs/0123456789abcdef/viewer',
                        data=b'{"view":"stress"}', headers={'Content-Type': 'application/json'})
                    with urllib.request.urlopen(request) as response:
                        self.assertEqual(json.load(response)['pid'], 1234)
                    self.assertEqual(opened.call_args.args[1:], ('0123456789abcdef', {'view': 'stress'}))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

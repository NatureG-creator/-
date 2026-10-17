import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.job_service import JobService
from backend.worker import run_job


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = JobService()
        self.service.initialize(Path(self.temp.name))
        job = self.service.create_job({'kind': 'apdl_tension', 'options': {
            'corrosion_mode': 'flat', 'nx': 3, 'ny': 2, 'layers': 1}}, launch=False)
        run_job(job['id'], self.service.runtime)
        self.id = job['id']
        self.output = self.service.runtime / 'jobs' / self.id / 'outputs'

    def tearDown(self):
        self.temp.cleanup()

    def test_custom_build_is_frozen_and_never_changes_source(self):
        from backend.apdl_commands import command_snapshot, check_commands
        before = (self.output / 'materials.mac').read_bytes()
        snapshot = command_snapshot(self.service, self.id)
        files = snapshot['files']
        files['materials.mac'] = 'MP,EX,1,190000\nMP,PRXY,1,0.3\n'
        payload = dict(kind='apdl_tension', source_job_id=self.id,
                       execution_mode='custom_commands', run_mode='build',
                       command_files=files, source_revision=snapshot['revision'])
        self.assertTrue(check_commands(self.service, payload)['changes'])
        job = self.service.create_job(payload, launch=False)
        files['materials.mac'] = 'MUTATED CLIENT'
        run_job(job['id'], self.service.runtime)
        state = self.service.get_job(job['id'])
        self.assertEqual(state['state'], 'completed', state.get('error'))
        out = self.service.runtime / 'jobs' / job['id'] / 'outputs'
        self.assertIn('190000', (out / 'materials.mac').read_text())
        summary = json.loads((out / 'summary.json').read_text(encoding='utf8'))
        self.assertEqual(summary['execution_mode'], 'custom_commands')
        self.assertEqual(summary['validation_state'], 'unverified_custom_commands')
        self.assertEqual((self.output / 'materials.mac').read_bytes(), before)
        self.assertTrue((out / 'command_revision.json').is_file())
        self.assertFalse((out / 'force_displacement.csv').exists())

    def test_missing_include_and_stale_revision_rejected(self):
        from backend.apdl_commands import command_snapshot, check_commands
        snapshot = command_snapshot(self.service, self.id)
        payload = dict(source_job_id=self.id, source_revision=snapshot['revision'],
                       command_files=snapshot['files'])
        payload['command_files']['main.inp'] += '\n/INPUT,missing,mac\n'
        with self.assertRaisesRegex(ValueError, 'missing'):
            check_commands(self.service, payload)
        payload['command_files'] = snapshot['files'].copy()
        payload['source_revision'] = 'stale'
        with self.assertRaisesRegex(ValueError, '变化|版本'):
            check_commands(self.service, payload)

    def test_path_escape_and_unknown_file_rejected(self):
        from backend.apdl_commands import command_snapshot, check_commands
        snapshot = command_snapshot(self.service, self.id)
        for files in ({'../escape.mac': 'FINISH'},
                      dict(snapshot['files'], **{'main.inp': '/INPUT,../../escape,mac'})):
            with self.subTest(files=list(files)), self.assertRaises(ValueError):
                check_commands(self.service, dict(source_job_id=self.id,
                    source_revision=snapshot['revision'], command_files=files))

    def test_custom_solve_uses_edited_deck_without_parameter_validation(self):
        from backend.apdl_commands import command_snapshot
        snapshot = command_snapshot(self.service, self.id)
        payload = dict(kind='apdl_tension', source_job_id=self.id,
                       execution_mode='custom_commands', run_mode='solve',
                       source_revision=snapshot['revision'], command_files=snapshot['files'])
        with patch('backend.apdl_solver.mapdl_capabilities', return_value={'available': True}):
            job = self.service.create_job(payload, launch=False)
        with patch('backend.apdl_solver.run_mapdl', return_value={'state': 'process_finished'}) as solve, \
             patch('backend.apdl_solver.read_tension_results') as validation:
            run_job(job['id'], self.service.runtime)
        solve.assert_called_once()
        validation.assert_not_called()

    def test_tampered_frozen_nodes_are_rejected(self):
        from backend.apdl_commands import command_snapshot
        snapshot=command_snapshot(self.service,self.id)
        job=self.service.create_job(dict(kind='apdl_tension',execution_mode='custom_commands',source_job_id=self.id,source_revision=snapshot['revision'],command_files=snapshot['files']),launch=False)
        (self.service.runtime/'jobs'/job['id']/'inputs/nodes.dat').write_text('changed')
        run_job(job['id'],self.service.runtime)
        state=self.service.get_job(job['id'])
        self.assertEqual(state['state'],'failed')
        self.assertRegex(state['error'],'变化|校验')


if __name__ == '__main__':
    unittest.main()

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.job_service import JobService
from backend.job_status import update_job_status
from backend.runner import _atomic_json
from backend.worker import run_job


class WorkerIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.runtime = Path(temporary.name)
        self.job_id = 'd' * 16
        self.job = self.runtime / 'jobs' / self.job_id
        self.job.mkdir(parents=True)
        self.status = self.job / 'status.json'
        self.state = dict(id=self.job_id, kind='simulation', state='queued', pid=None,
                          process_created_at=42., created_at=1, updated_at=1)
        self.spec = dict(kind='simulation', config={'mode': 'pycharm'})
        _atomic_json(self.status, self.state)
        _atomic_json(self.job / 'spec.json', self.spec)

    def test_running_pid_and_creation_time_are_published_together(self):
        changes = []
        def update(path, value, **options):
            changes.append(dict(value))
            return update_job_status(path, value, **options)
        process = Mock()
        process.create_time.return_value = 99.
        with patch('psutil.Process', return_value=process), patch(
                'backend.job_status.update_job_status', side_effect=update), patch(
                'backend.worker.run_simulation', return_value={}), patch(
                'backend.task_io.job_io', return_value={}), patch('backend.task_io.export_outputs'):
            run_job(self.job_id, self.runtime)
        running = next(value for value in changes if value.get('state') == 'running')
        self.assertEqual(running.get('pid'), os.getpid())
        self.assertEqual(running.get('process_created_at'), 99.)
        self.assertEqual(json.loads(self.status.read_text(encoding='utf-8'))['state'], 'completed')

    def test_missing_identity_dependency_does_not_start_computation(self):
        with patch.dict('sys.modules', {'psutil': None}), patch(
                'backend.worker.run_simulation', return_value={}) as compute, patch(
                'backend.task_io.job_io', return_value={}), patch(
                'backend.task_io.export_outputs'), contextlib.redirect_stderr(io.StringIO()):
            run_job(self.job_id, self.runtime)
        state = json.loads(self.status.read_text(encoding='utf-8'))
        self.assertEqual(state['state'], 'failed')
        self.assertIn('psutil', state['error'])
        compute.assert_not_called()
        self.assertFalse((self.job / 'worker.lock').exists())

    def test_resume_clears_previous_process_identity_before_launch(self):
        service = JobService()
        service.initialize(self.runtime)
        state = dict(self.state, state='interrupted', pid=999999999, spec=self.spec)
        with patch.object(service, 'get_job', return_value=state), patch(
                'backend.job_service.process_alive', return_value=False), patch(
                'backend.runner.precheck_resume', return_value={'available': True}), patch.object(service, 'launch'):
            result = service.resume(self.job_id)
        self.assertEqual(result['state'], 'queued')
        self.assertIsNone(result['pid'])
        self.assertIsNone(result.get('process_created_at'))
        self.assertIsNone(json.loads(self.status.read_text(encoding='utf-8')).get('process_created_at'))


if __name__ == '__main__':
    unittest.main()

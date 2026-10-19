import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

from backend.job_service import JobService
from backend.runner import _atomic_json
from backend.server import make_server


class JobHistoryTests(unittest.TestCase):
    def test_batch_deletes_only_confirmed_ended_tasks(self):
        from backend.job_history import delete_jobs
        other='b'*16
        self.make_job(other)
        ids=[self.job_id,other]
        for invalid in ([{}],ids+ids):
            with self.assertRaises(ValueError):delete_jobs(self.service,invalid,invalid)
        with self.assertRaises(ValueError):delete_jobs(self.service,ids,list(reversed(ids)))
        result=delete_jobs(self.service,ids,ids)
        self.assertEqual(result['deleted_ids'],ids)
        self.assertFalse(self.folder.exists())
        self.assertFalse((self.service.runtime/'jobs'/other).exists())

    def test_batch_preflight_keeps_all_files_when_one_task_is_active(self):
        other='b'*16
        self.make_job(other,state='running',pid=123)
        from backend.job_history import delete_jobs
        with self.assertRaises(ValueError):
            delete_jobs(self.service,[self.job_id,other],[self.job_id,other])
        self.assertTrue(self.folder.exists())
        self.assertTrue((self.service.runtime/'jobs'/other).exists())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = JobService()
        self.service.initialize(Path(self.temp.name))
        self.job_id = 'a' * 16
        self.folder = self.make_job(self.job_id)

    def make_job(self, job_id, state='interrupted', **fields):
        folder = self.service.runtime / 'jobs' / job_id
        (folder / 'outputs').mkdir(parents=True)
        record=dict(id=job_id, kind='simulation', state=state, pid=None, created_at=1)
        record.update(fields)
        _atomic_json(folder / 'status.json', record)
        _atomic_json(folder / 'spec.json', dict(kind='simulation', config={'mode': 'strict'}))
        (folder / 'outputs' / 'result.npz').write_bytes(b'preserve results')
        (folder / 'checkpoints').mkdir()
        (folder / 'checkpoints' / 'progress.json').write_text('{}', encoding='utf-8')
        return folder

    def test_hide_unhide_preserves_original_status_results_and_checkpoint(self):
        before = {p.relative_to(self.folder): p.read_bytes() for p in self.folder.rglob('*') if p.is_file()}
        self.service.set_job_hidden(self.job_id, True)
        self.assertTrue(self.service.get_job(self.job_id)['history_hidden'])
        self.assertEqual(self.service.list_jobs(include_hidden=False), [])
        self.assertEqual(len(self.service.list_jobs()), 1)
        self.service.set_job_hidden(self.job_id, False)
        self.assertFalse(self.service.get_job(self.job_id)['history_hidden'])
        for path, data in before.items():
            self.assertEqual((self.folder / path).read_bytes(), data)

    def test_limit_applies_after_hidden_filter(self):
        self.service.set_job_hidden(self.job_id, True)
        other = 'b' * 16
        self.make_job(other)
        self.assertEqual([job['id'] for job in self.service.list_jobs(include_hidden=False, limit=1)], [other])

    def test_delete_requires_confirmation_and_preserves_exported_files(self):
        external = self.service.runtime / 'external-export'
        external.mkdir()
        (external / 'result.npz').write_bytes(b'keep exported result')
        _atomic_json(self.folder / 'task_io.json', {'export_directory': str(external)})
        with self.assertRaisesRegex(ValueError, '确认'):
            self.service.delete_job(self.job_id, '')
        self.service.delete_job(self.job_id, self.job_id)
        self.assertFalse(self.folder.exists())
        self.assertEqual((external / 'result.npz').read_bytes(), b'keep exported result')

    def test_active_states_cannot_be_hidden_or_deleted(self):
        for state in ('queued', 'running', 'stop_failed'):
            _atomic_json(self.folder / 'status.json', dict(id=self.job_id, kind='simulation', state=state, pid=None))
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.service.set_job_hidden(self.job_id, True)
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.service.delete_job(self.job_id, self.job_id)

    def test_finished_state_cannot_bypass_live_worker_or_export(self):
        for fields in ({'pid': 123}, {'export_pending': True}):
            _atomic_json(self.folder / 'status.json', dict(id=self.job_id, kind='simulation', state='failed', **fields))
            with patch('backend.job_history.process_alive', side_effect=lambda pid: pid == 123):
                with self.assertRaises(ValueError):
                    self.service.delete_job(self.job_id, self.job_id)
        _atomic_json(self.folder / 'status.json', dict(id=self.job_id, kind='simulation', state='failed'))
        process = Mock()
        process.poll.return_value = None
        self.service.processes[self.job_id] = process
        with self.assertRaises(ValueError):
            self.service.delete_job(self.job_id, self.job_id)

    def test_hidden_dependent_and_batch_references_block_deletion(self):
        other = self.make_job('b' * 16)
        _atomic_json(other / 'spec.json', {'source_job_id': self.job_id})
        self.service.set_job_hidden('b' * 16, True)
        with self.assertRaisesRegex(ValueError, '引用'):
            self.service.delete_job(self.job_id, self.job_id)
        _atomic_json(other / 'spec.json', {})
        batch = self.service.runtime / 'batches' / ('c' * 16)
        batch.mkdir()
        _atomic_json(batch / 'status.json', {'job_ids': [self.job_id]})
        with self.assertRaisesRegex(ValueError, '批次'):
            self.service.delete_job(self.job_id, self.job_id)

    def test_path_reference_also_blocks_deletion(self):
        other = self.make_job('b' * 16)
        _atomic_json(other / 'spec.json', {'input': str(self.folder / 'outputs' / 'result.npz')})
        with self.assertRaisesRegex(ValueError, '引用'):
            self.service.delete_job(self.job_id, self.job_id)

    def test_worker_lock_and_pending_launch_block_deletion(self):
        (self.folder / 'worker.lock').write_text('123', encoding='ascii')
        with patch('backend.job_history.process_alive', side_effect=lambda pid: pid == 123):
            with self.assertRaises(ValueError):
                self.service.delete_job(self.job_id, self.job_id)
        (self.folder / 'worker.lock').unlink()
        self.service.pending_jobs.add(self.job_id)
        with self.assertRaises(ValueError):
            self.service.delete_job(self.job_id, self.job_id)

    def test_invalid_id_cannot_delete_outside_jobs(self):
        with self.assertRaises(FileNotFoundError):
            self.service.delete_job('../external', '../external')
        self.assertTrue(self.folder.is_dir())

    def test_apdl_solver_must_be_confirmed_finished_even_if_worker_ended(self):
        _atomic_json(self.folder / 'status.json', dict(id=self.job_id, kind='apdl_tension', state='completed'))
        _atomic_json(self.folder / 'outputs' / 'mapdl_process.json', {'state': 'running', 'pid': 123})
        with patch('backend.job_history.process_alive', side_effect=lambda pid: pid == 123):
            with self.assertRaisesRegex(ValueError, '求解'):
                self.service.delete_job(self.job_id, self.job_id)

    def test_hidden_job_can_resume_without_changing_checkpoint(self):
        self.service.set_job_hidden(self.job_id, True)
        progress = self.folder / 'checkpoints' / 'progress.json'
        before = progress.read_bytes()
        with patch('backend.runner.precheck_resume', return_value={'available': True}), patch.object(self.service, 'launch'):
            state = self.service.resume(self.job_id)
        self.assertEqual(state['state'], 'queued')
        self.assertEqual(progress.read_bytes(), before)

    def test_unreadable_reference_record_blocks_deletion(self):
        other = self.make_job('b' * 16)
        (other / 'spec.json').write_text('{broken', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '引用'):
            self.service.delete_job(self.job_id, self.job_id)


class JobHistoryApiTests(unittest.TestCase):
    def test_history_actions_and_filter_do_not_remove_hidden_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            server = make_server('127.0.0.1', 0, Path(folder))
            server.log_requests = False
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            job_id = 'd' * 16
            job = Path(folder) / 'jobs' / job_id
            job.mkdir()
            _atomic_json(job / 'status.json', dict(id=job_id, kind='simulation', state='failed', pid=None))
            _atomic_json(job / 'spec.json', dict(kind='simulation', config={'mode': 'pycharm'}))

            def request(path, body=None):
                req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                             headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req) as response:
                    return json.load(response)

            try:
                request(f'/api/jobs/{job_id}/hide', {})
                self.assertEqual(request('/api/jobs?include_hidden=0'), [])
                self.assertEqual(len(request('/api/jobs')), 1)
                self.assertTrue(request('/api/jobs')[0]['history_hidden'])
                request(f'/api/jobs/{job_id}/unhide', {})
                self.assertEqual(len(request('/api/jobs?include_hidden=0')), 1)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request(f'/api/jobs/{job_id}/delete', {})
                self.assertEqual(error.exception.code, 400)
                request(f'/api/jobs/{job_id}/delete', {'confirm_job_id': job_id})
                self.assertFalse(job.exists())
            finally:
                server.shutdown()
                server.server_close()
                thread.join(5)


if __name__ == '__main__':
    unittest.main()

import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.job_service import JobService
from backend.runner import _atomic_json
from backend.worker import run_job


class OriginServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = JobService()
        self.service.initialize(Path(self.temp.name))
        self.source_id = 'a' * 16
        self.source = self.service.runtime / 'jobs' / self.source_id
        self.source.mkdir()
        _atomic_json(self.source / 'status.json', dict(id=self.source_id, kind='fitting', state='completed'))
        self.engine = types.ModuleType('backend.origin_plotting')
        self.engine.prepare_origin = Mock(return_value=dict(kind='origin_plot', source_job_id=self.source_id))
        self.engine.freeze_origin = Mock()
        self.engine.run_origin = Mock(return_value={'project': 'origin_project.opju'})
        self.engine.open_origin_project = Mock(return_value={'opened': True})
        self.engine.stop_origin_process = Mock()
        self.modules = patch.dict('sys.modules', {'backend.origin_plotting': self.engine})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def tearDown(self):
        deadline = time.monotonic() + 3
        while self.service._launching_jobs and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.service._launching_jobs, 'Origin scheduler did not finish')

    def create(self):
        return self.service.create_job(dict(kind='origin_plot', source_job_id=self.source_id), launch=False)

    def test_freezes_completed_fitting_and_dispatches_worker(self):
        job = self.create()
        folder = self.service.runtime / 'jobs' / job['id']
        self.engine.prepare_origin.assert_called_once_with(dict(kind='origin_plot', source_job_id=self.source_id), self.source)
        self.engine.freeze_origin.assert_called_once_with(self.engine.prepare_origin.return_value, self.source, folder)
        run_job(job['id'], self.service.runtime)
        self.assertEqual(self.service.get_job(job['id'])['state'], 'completed')
        self.engine.run_origin.assert_called_once()
        self.assertEqual(self.engine.run_origin.call_args.args[:2], (folder, self.engine.prepare_origin.return_value))

    def test_rejects_invalid_and_unfinished_source_before_prepare(self):
        for source in ('../' + self.source_id, None, 'A' * 16):
            with self.assertRaises(FileNotFoundError):
                self.service.create_job(dict(kind='origin_plot', source_job_id=source), launch=False)
        for kind, state in (('simulation', 'completed'), ('fitting', 'running')):
            _atomic_json(self.source / 'status.json', dict(id=self.source_id, kind=kind, state=state, pid=999999999))
            with self.assertRaisesRegex(ValueError, '拟合'):
                self.create()
        self.engine.prepare_origin.assert_not_called()

    def test_origin_bypasses_compute_slots_and_benchmark_gate(self):
        job = self.create()
        self.service.compute_slots.acquire()
        self.service.compute_slots.acquire()
        self.service.benchmark_gate.acquire()
        self.addCleanup(self.service.benchmark_gate.release)
        self.addCleanup(self.service.compute_slots.release)
        self.addCleanup(self.service.compute_slots.release)
        started = threading.Event()
        process = Mock()
        process.wait.side_effect = lambda: started.set()
        with patch.object(self.service, '_start_process', return_value=process):
            self.service.launch(job['id'])
            self.assertTrue(started.wait(2), 'Origin was blocked by compute scheduling')

    def test_open_requires_completed_origin_job(self):
        job = self.create()
        with self.assertRaises(ValueError):
            self.service.open_origin(job['id'])
        folder = self.service.runtime / 'jobs' / job['id']
        _atomic_json(folder / 'status.json', dict(id=job['id'], kind='origin_plot', state='completed'))
        self.assertEqual(self.service.open_origin(job['id']), {'opened': True})
        self.engine.open_origin_project.assert_called_once_with(folder)

    def test_origin_queue_is_serial(self):
        first, second = self.create(), self.create()
        entered, release, second_entered = threading.Event(), threading.Event(), threading.Event()
        first_process, second_process = Mock(), Mock()
        first_process.wait.side_effect = lambda: (entered.set(), release.wait(3))
        second_process.wait.side_effect = second_entered.set
        with patch.object(self.service, '_start_process', side_effect=[first_process, second_process]):
            self.service.launch(first['id'])
            self.assertTrue(entered.wait(2))
            self.service.launch(second['id'])
            self.assertFalse(second_entered.wait(.1))
            release.set()
            self.assertTrue(second_entered.wait(2))

    def test_freeze_failure_removes_incomplete_job(self):
        before = set((self.service.runtime / 'jobs').iterdir())
        self.engine.freeze_origin.side_effect = ValueError('source changed')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            self.create()
        self.assertEqual(set((self.service.runtime / 'jobs').iterdir()), before)

    def test_worker_failure_is_reported(self):
        job = self.create()
        self.engine.run_origin.side_effect = RuntimeError('Origin unavailable')
        with patch('backend.worker.traceback.print_exc'):
            run_job(job['id'], self.service.runtime)
        state = self.service.get_job(job['id'])
        self.assertEqual(state['state'], 'failed')
        self.assertEqual(state['error'], 'Origin unavailable')
        self.assertFalse((self.service.runtime / 'jobs' / job['id'] / 'worker.lock').exists())

    def test_stop_uses_only_owned_origin_cleanup_after_worker_exit(self):
        job = self.create()
        folder = self.service.runtime / 'jobs' / job['id']
        _atomic_json(folder / 'status.json', dict(id=job['id'], kind='origin_plot', state='running', pid=999999999, created_at=1))
        process = Mock()
        process.poll.return_value = None
        self.service.processes[job['id']] = process
        with patch('backend.process_control.verify_worker_process') as verify, patch('backend.process_control.stop_verified_process') as stop:
            state = self.service.stop(job['id'])
        self.assertEqual(state['state'], 'interrupted')
        verify.assert_called_once()
        stop.assert_called_once_with(verify.return_value)
        process.wait.assert_called_once()
        self.engine.stop_origin_process.assert_called_once_with(folder)

    def test_inherited_origin_does_not_reserve_compute_slots(self):
        folder = self.service.runtime / 'jobs' / ('b' * 16)
        folder.mkdir()
        (folder / 'worker.lock').write_text('1234', encoding='ascii')
        _atomic_json(folder / 'status.json', dict(kind='origin_plot', state='running', pid=1234))
        with patch('backend.job_service.process_alive', return_value=True), patch('backend.job_service.threading.Thread'):
            self.service.initialize(self.service.runtime)
        self.assertEqual(self.service.inherited_processes, {'b' * 16: 1234})
        self.assertTrue(self.service.compute_slots.acquire(blocking=False))
        self.assertTrue(self.service.compute_slots.acquire(blocking=False))

    def test_dead_worker_cleanup_failure_can_be_retried_with_stop(self):
        job = self.create()
        folder = self.service.runtime / 'jobs' / job['id']
        _atomic_json(folder / 'status.json', dict(id=job['id'], kind='origin_plot', state='running', pid=999999999, created_at=1))
        self.engine.stop_origin_process.side_effect = PermissionError('owned Origin still alive')
        state = self.service.get_job(job['id'])
        self.assertEqual(state['state'], 'stop_failed')
        self.assertIn('owned Origin still alive', state['stop_error'])
        self.engine.stop_origin_process.side_effect = None
        self.assertEqual(self.service.stop(job['id'])['state'], 'interrupted')
        self.assertEqual(self.engine.stop_origin_process.call_count, 2)

    def test_next_origin_waits_for_inherited_worker_and_failed_cleanup(self):
        previous, next_job = self.create(), self.create()
        folder = self.service.runtime / 'jobs' / previous['id']
        _atomic_json(folder / 'status.json', dict(id=previous['id'], kind='origin_plot', state='running', pid=999999999, created_at=1))
        self.engine.stop_origin_process.side_effect = PermissionError('retry required')
        started = threading.Event()
        process = Mock()
        process.wait.side_effect = started.set
        with patch('backend.job_service.process_alive', return_value=False), patch.object(self.service, '_start_process', return_value=process):
            self.service.launch(next_job['id'])
            self.assertFalse(started.wait(.2))
            self.assertEqual(self.service.get_job(previous['id'])['state'], 'stop_failed')
            self.engine.stop_origin_process.side_effect = None
            self.service.stop(previous['id'])
            self.assertTrue(started.wait(2))

    def test_origin_waits_for_live_inherited_worker(self):
        previous, next_job = self.create(), self.create()
        folder = self.service.runtime / 'jobs' / previous['id']
        _atomic_json(folder / 'status.json', dict(id=previous['id'], kind='origin_plot', state='running', pid=999999999, created_at=1))
        started = threading.Event()
        process = Mock()
        process.wait.side_effect = started.set
        with patch('backend.job_service.process_alive', side_effect=lambda pid: pid == 999999999), patch.object(self.service, '_start_process', return_value=process):
            self.service.launch(next_job['id'])
            self.assertFalse(started.wait(.2))
            _atomic_json(folder / 'status.json', dict(id=previous['id'], kind='origin_plot', state='completed', created_at=1))
            self.assertTrue(started.wait(2))


class OriginApiTests(unittest.TestCase):
    from backend.tests.test_finite_element_api import FiniteElementApiTests as fixture
    setUp = fixture.setUp
    tearDown = fixture.tearDown
    request = fixture.request

    def test_origin_routes(self):
        engine = types.ModuleType('backend.origin_plotting')
        engine.origin_capabilities = Mock(return_value={'available': False})
        with patch.dict('sys.modules', {'backend.origin_plotting': engine}):
            self.assertEqual(self.request('/api/origin/capabilities'), (200, {'available': False}))
        with patch.object(self.server, 'create_job', return_value={'id': 'a' * 16}) as create:
            self.assertEqual(self.request('/api/origin/jobs', {'source_job_id': 'b' * 16})[0], 201)
            create.assert_called_once_with({'source_job_id': 'b' * 16, 'kind': 'origin_plot'})
        with patch.object(self.server, 'open_origin', return_value={'opened': True}) as open_project:
            self.assertEqual(self.request('/api/origin/jobs/' + 'a' * 16 + '/open', {})[0], 200)
            open_project.assert_called_once_with('a' * 16)


if __name__ == '__main__':
    unittest.main()

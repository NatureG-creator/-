import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.job_service import JobService
from backend.runner import _atomic_json


class JobStopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service=JobService()
        self.service.initialize(Path(self.temp.name))
        self.job_id='c'*16
        self.job=self.service.runtime/'jobs'/self.job_id
        (self.job/'outputs').mkdir(parents=True)
        self.status=self.job/'status.json'
        _atomic_json(self.status,dict(id=self.job_id,kind='simulation',state='running',pid=999999999,
                                     process_created_at=42.,created_at=1,started_at=1,updated_at=1))
        _atomic_json(self.job/'spec.json',dict(kind='simulation',config={'mode':'strict'}))
        self.process=Mock(pid=999999999)
        self.process.poll.return_value=None
        self.service.processes[self.job_id]=self.process

    def test_owned_stop_permission_failure_is_persisted_and_retryable(self):
        with patch('backend.process_control.verify_worker_process') as verify, patch(
                'backend.process_control.stop_verified_process',side_effect=PermissionError('拒绝停止测试进程')), patch(
                'backend.job_service.subprocess.run'):
            with self.assertRaisesRegex(ValueError,'停止失败'):
                self.service.stop(self.job_id)
        state=json.loads(self.status.read_text(encoding='utf-8'))
        self.assertEqual(state['state'],'stop_failed')
        self.assertIn('拒绝',state['stop_error'])
        verify.assert_called_once()
        self.process.wait.assert_not_called()

    def test_owned_worker_identity_must_be_verified_before_any_stop(self):
        with patch('backend.process_control.verify_worker_process',side_effect=ValueError('PID被复用')), patch(
                'backend.process_control.stop_verified_process') as stop, patch('backend.job_service.subprocess.run'):
            with self.assertRaisesRegex(ValueError,'停止失败'):
                self.service.stop(self.job_id)
        stop.assert_not_called()
        self.assertEqual(json.loads(self.status.read_text(encoding='utf-8'))['state'],'stop_failed')

    def test_verified_owned_worker_stop_has_confirmed_completion(self):
        with patch('backend.process_control.verify_worker_process') as verify, patch(
                'backend.process_control.stop_verified_process') as stop, patch('backend.job_service.subprocess.run'):
            result=self.service.stop(self.job_id)
        self.assertEqual(result['state'],'interrupted')
        stop.assert_called_once_with(verify.return_value)
        self.process.wait.assert_called_once_with(timeout=20)

    def apdl_job(self):
        state=json.loads(self.status.read_text(encoding='utf-8'))
        state['kind']='apdl_tension'
        _atomic_json(self.status,state)
        _atomic_json(self.job/'spec.json',dict(kind='apdl_tension',run_mode='solve'))
        _atomic_json(self.job/'outputs'/'summary.json',dict(build_state='built',solve_state='running',
                     started_at=1,stage_started_at={'solver':1},stage_states={'solver':'running'},timing={}))

    def test_apdl_cleanup_failure_preserves_retry_then_records_confirmed_stop(self):
        self.apdl_job()
        with patch('backend.process_control.verify_worker_process'), patch(
                'backend.process_control.stop_verified_process') as worker_stop, patch(
                'backend.apdl_process.stop_owned_execution',return_value={'state':'failed','error':'权限不足'}):
            with self.assertRaisesRegex(ValueError,'停止失败'):
                self.service.stop(self.job_id)
        worker_stop.assert_not_called()
        self.assertEqual(json.loads(self.status.read_text(encoding='utf-8'))['state'],'stop_failed')
        with patch('backend.process_control.verify_worker_process'), patch(
                'backend.process_control.stop_verified_process'), patch(
                'backend.apdl_process.stop_owned_execution',return_value={'state':'stopped','verified_empty':True}) as cleanup:
            result=self.service.stop(self.job_id)
        self.assertEqual(cleanup.call_count,2)
        self.assertEqual(result['state'],'interrupted')
        self.assertNotIn('stop_error',result)
        self.assertNotIn('完整个体',result['error'])
        summary=json.loads((self.job/'outputs'/'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['solve_state'],'stopped')
        self.assertEqual(summary['stage_states']['solver'],'interrupted')
        self.assertGreater(summary['timing']['solver_seconds'],0)

    def test_apdl_second_cleanup_must_confirm_empty_after_worker_stops(self):
        self.apdl_job()
        with patch('backend.process_control.verify_worker_process'), patch(
                'backend.process_control.stop_verified_process') as worker_stop, patch(
                'backend.apdl_process.stop_owned_execution',side_effect=[{'state':'not_started'},
                    {'state':'stopped','verified_empty':False}]):
            with self.assertRaisesRegex(ValueError,'未确认'):
                self.service.stop(self.job_id)
        worker_stop.assert_called_once()
        self.assertEqual(json.loads(self.status.read_text(encoding='utf-8'))['state'],'stop_failed')

    def test_worker_failure_cannot_erase_pending_apdl_stop_retry(self):
        self.apdl_job()
        with patch('backend.process_control.verify_worker_process'), patch(
                'backend.apdl_process.stop_owned_execution',return_value={'state':'failed','error':'权限不足'}):
            with self.assertRaises(ValueError): self.service.stop(self.job_id)
        state=json.loads(self.status.read_text(encoding='utf-8'))
        state.update(state='failed',error='worker收尾写回')
        _atomic_json(self.status,state)
        self.assertEqual(self.service.get_job(self.job_id)['state'],'stop_failed')

    def test_autonomous_solver_cleanup_failure_remains_retryable(self):
        self.apdl_job()
        state=json.loads(self.status.read_text(encoding='utf-8'))
        state.update(state='failed',error='MAPDL监管组清理失败')
        _atomic_json(self.status,state)
        _atomic_json(self.job/'outputs'/'mapdl_execution.json',dict(state='failed',
                     cleanup={'state':'failed','verified_empty':False,'error':'cleanup denied'}))
        self.process.poll.return_value=1
        self.assertEqual(self.service.get_job(self.job_id)['state'],'stop_failed')

    def test_dead_apdl_worker_requires_group_verification_before_interrupted(self):
        self.apdl_job()
        self.process.poll.return_value=1
        with patch('backend.apdl_process.stop_owned_execution',return_value={'state':'failed','error':'组仍在运行'}) as cleanup:
            state=self.service.get_job(self.job_id)
        self.assertEqual(state['state'],'stop_failed')
        cleanup.assert_called_once()

    def test_legacy_solver_without_supervision_is_not_reported_empty(self):
        self.apdl_job()
        _atomic_json(self.job/'outputs'/'mapdl_execution.json',dict(state='running',pid=12345))
        with patch('backend.process_control.verify_worker_process'), patch(
                'backend.apdl_process.stop_owned_execution') as cleanup:
            with self.assertRaisesRegex(ValueError,'旧版任务'):
                self.service.stop(self.job_id)
        cleanup.assert_not_called()

    def test_malformed_control_record_keeps_task_readable_and_stop_retryable(self):
        self.apdl_job()
        _atomic_json(self.job/'outputs'/'mapdl_process.json',['damaged-record'])
        self.assertEqual(self.service.get_job(self.job_id)['state'],'stop_failed')

    def test_stop_marker_denied_keeps_original_error_and_worker_cannot_erase_retry(self):
        self.apdl_job()
        from backend.runner import _atomic_json as real_write
        def write(path,value):
            if path.name=='apdl_stop.json': raise PermissionError('stop marker denied')
            return real_write(path,value)
        with patch('backend.job_service._atomic_json',side_effect=write), patch(
                'backend.process_control.verify_worker_process',side_effect=ValueError('original identity failure')):
            with self.assertRaisesRegex(ValueError,'original identity failure'):
                self.service.stop(self.job_id)
        self.assertEqual(json.loads(self.status.read_text(encoding='utf-8'))['state'],'stop_failed')
        from backend.job_status import update_job_status
        update_job_status(self.status,{'state':'failed','error':'worker final failure'})
        self.assertEqual(self.service.get_job(self.job_id)['state'],'stop_failed')

    def test_dead_worker_marker_write_denied_does_not_make_task_unreadable(self):
        self.apdl_job()
        self.process.poll.return_value=1
        from backend.runner import _atomic_json as real_write
        def write(path,value):
            if path.name=='apdl_stop.json': raise PermissionError('stop marker denied')
            return real_write(path,value)
        with patch('backend.job_service._atomic_json',side_effect=write), patch(
                'backend.apdl_process.stop_owned_execution',return_value={'state':'failed','error':'original cleanup failure'}):
            state=self.service.get_job(self.job_id)
        self.assertEqual(state['state'],'stop_failed')
        self.assertIn('marker denied',state['stop_persistence_error'])

    def test_empty_truncated_or_unreadable_control_record_does_not_disable_safe_stop(self):
        self.apdl_job()
        path=self.job/'outputs'/'mapdl_process.json'
        for content in (b'',b'{',b'\xff'):
            with self.subTest(content=content):
                path.write_bytes(content)
                self.assertEqual(self.service.get_job(self.job_id)['state'],'stop_failed')
                with patch('backend.process_control.verify_worker_process'), patch(
                        'backend.process_control.stop_verified_process') as worker_stop:
                    with self.assertRaisesRegex(ValueError,'停止失败'):
                        self.service.stop(self.job_id)
                worker_stop.assert_not_called()
        from backend.job_service import json_record as real_read
        def read(candidate,*args):
            if candidate==path: raise PermissionError('control read denied')
            return real_read(candidate,*args)
        with patch('backend.job_service.json_record',side_effect=read):
            self.assertEqual(self.service.get_job(self.job_id)['state'],'stop_failed')

    def test_truncated_stop_record_does_not_prevent_service_initialize(self):
        self.apdl_job()
        (self.job/'worker.lock').write_text('999999999',encoding='ascii')
        (self.job/'outputs'/'apdl_stop.json').write_text('{',encoding='utf-8')
        service=JobService()
        service.initialize(self.service.runtime)
        service.processes[self.job_id]=self.process
        self.assertEqual(service.get_job(self.job_id)['state'],'stop_failed')


if __name__=='__main__':
    unittest.main()

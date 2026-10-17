import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.io import loadmat, savemat

from backend.job_service import JobService
from backend.runner import _atomic_json
from backend.worker import run_job


class TaskIOTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = JobService()
        self.service.initialize(self.root / 'runtime')

    def tearDown(self):
        self.temp.cleanup()

    def completed(self, kind='fitting'):
        job = self.service.create_job({'kind': 'diagnostics'}, launch=False)
        folder = self.service.runtime / 'jobs' / job['id']
        _atomic_json(folder / 'spec.json', {'kind': kind, 'case_name': '原始名称'})
        _atomic_json(folder / 'status.json', dict(job, kind=kind, state='completed'))
        (folder / 'outputs').mkdir()
        (folder / 'outputs' / '结果.csv').write_text('x,y\n1,2\n', encoding='utf-8')
        return job['id'], folder

    def test_all_tasks_save_name_and_export_settings(self):
        job = self.service.create_job({'kind': 'diagnostics', 'case_name': '本机检查',
                                      'export_directory': str(self.root / '成果')}, launch=False)
        state = self.service.get_job(job['id'])
        self.assertEqual(state['display_name'], '本机检查')
        self.assertEqual(state['task_io']['export_directory'], str(self.root / '成果'))

    def test_rename_preserves_frozen_scientific_spec(self):
        from backend.task_io import configure_job
        job_id, folder = self.completed()
        before = (folder / 'spec.json').read_bytes()
        configure_job(self.service, job_id, {'name': '自定义实验名称'})
        self.assertEqual(self.service.get_job(job_id)['display_name'], '自定义实验名称')
        self.assertEqual((folder / 'spec.json').read_bytes(), before)
        other = JobService()
        other.initialize(self.service.runtime)
        self.assertEqual(other.get_job(job_id)['display_name'], '自定义实验名称')

    def test_old_job_falls_back_to_original_name(self):
        job_id, folder = self.completed()
        (folder / 'task_io.json').unlink(missing_ok=True)
        self.assertEqual(self.service.get_job(job_id)['display_name'], '原始名称')

    def test_export_to_chosen_directory_never_overwrites(self):
        from backend.task_io import configure_job, export_job
        job_id, folder = self.completed()
        configure_job(self.service, job_id, {'name': '试验/A', 'export_directory': str(self.root / '导出')})
        first = export_job(self.service, job_id)
        second = export_job(self.service, job_id)
        self.assertNotEqual(first['path'], second['path'])
        self.assertEqual(Path(first['path']).parent, self.root / '导出')
        self.assertEqual((Path(first['path']) / 'outputs' / '结果.csv').read_bytes(),
                         (folder / 'outputs' / '结果.csv').read_bytes())
        self.assertTrue((Path(second['path']) / 'spec.json').is_file())
        exported = json.loads((Path(second['path']) / 'task_io.json').read_text(encoding='utf-8'))
        self.assertEqual(exported['last_export']['path'], second['path'])

    def test_export_rejects_active_job_and_runtime_destination(self):
        from backend.task_io import configure_job, export_job
        job = self.service.create_job({'kind': 'diagnostics'}, launch=False)
        configure_job(self.service, job['id'], {'export_directory': str(self.root / '导出')})
        with self.assertRaisesRegex(ValueError, '结束'):
            export_job(self.service, job['id'])
        with self.assertRaisesRegex(ValueError, '任务目录'):
            configure_job(self.service, job['id'], {'export_directory': str(self.service.runtime / 'jobs')})

    def test_export_failure_is_reported_and_outputs_preserved(self):
        from backend.task_io import configure_job, export_job
        job_id, folder = self.completed()
        blocked = self.root / '不是目录'
        blocked.write_text('保留', encoding='utf-8')
        configure_job(self.service, job_id, {'export_directory': str(blocked)})
        result = export_job(self.service, job_id)
        self.assertEqual(result['state'], 'failed')
        self.assertTrue((folder / 'outputs' / '结果.csv').is_file())
        self.assertEqual(self.service.get_job(job_id)['task_io']['last_export']['state'], 'failed')

    def test_invalid_io_rejected_before_task_created(self):
        for fields in ({'case_name': 'a' * 101}, {'case_name': {'bad': 1}},
                       {'export_directory': 'relative/path'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.service.create_job(dict(kind='diagnostics', **fields), launch=False)
        self.assertEqual(list((self.service.runtime / 'jobs').iterdir()), [])

    def test_uploaded_mat_freezes_and_runs_legacy_surface_export(self):
        stream = io.BytesIO()
        expected = np.arange(6).reshape(2, 3) / 100
        savemat(stream, {'Z_filled': np.zeros((2, 3)), 'F_filled': expected})
        data = stream.getvalue()
        upload = self.service.upload('实测表面.mat', io.BytesIO(data), len(data))
        job = self.service.create_job({'kind': 'finite_element', 'upload_id': upload['id'],
            'source_kind': 'measured', 'case_name': '表面导出',
            'export_directory': str(self.root / '成果'),
            'input_variable': 'F_filled', 'options': {'output_variable': 'Z_filled'}}, launch=False)
        self.service.get_upload(upload['id'])[1].unlink()
        run_job(job['id'], self.service.runtime)
        state = self.service.get_job(job['id'])
        self.assertEqual(state['state'], 'completed', state.get('error'))
        self.assertFalse(state['export_pending'])
        self.assertEqual(state['task_io']['last_export']['state'], 'completed')
        np.testing.assert_array_equal(loadmat(self.service.runtime / 'jobs' / job['id'] / 'outputs' / 'Z_filled.mat')['Z_filled'], expected)
        self.assertTrue((Path(state['task_io']['last_export']['path']) / 'outputs' / 'Z_filled.mat').exists())

    def test_upload_hash_and_type_are_validated(self):
        upload = self.service.upload('wrong.csv', io.BytesIO(b'1,2\n3,4'), 7)
        with self.assertRaisesRegex(ValueError, 'MAT'):
            self.service.create_job({'kind': 'finite_element', 'upload_id': upload['id'],
                                     'source_kind': 'measured'}, launch=False)
        data = io.BytesIO()
        np.savez(data, perfect_a=np.ones((2, 3, 4)))
        raw = data.getvalue()
        upload = self.service.upload('ca.npz', io.BytesIO(raw), len(raw))
        with self.assertRaisesRegex(ValueError, '大于0'):
            self.service.create_job({'kind': 'finite_element', 'upload_id': upload['id'],
                'source_kind': 'simulation', 'options': {'grid_spacing_mm': 0}}, launch=False)
        self.service.get_upload(upload['id'])[1].write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '修改'):
            self.service.create_job({'kind': 'finite_element', 'upload_id': upload['id'],
                                     'source_kind': 'simulation'}, launch=False)

    def test_export_can_be_retried_if_copy_worker_exited(self):
        job_id, folder = self.completed()
        from backend.task_io import configure_job, export_job
        configure_job(self.service, job_id, {'export_directory': str(self.root / '导出')})
        state = json.loads((folder / 'status.json').read_text(encoding='utf-8'))
        _atomic_json(folder / 'status.json', dict(state, export_pending=True, pid=None))
        self.assertEqual(export_job(self.service, job_id)['state'], 'completed')
        self.assertEqual(self.service.get_job(job_id)['task_io']['last_export']['state'], 'completed')

    def test_worker_export_failure_does_not_fail_scientific_result(self):
        blocked = self.root / '是文件'
        blocked.write_text('保留', encoding='utf-8')
        job = self.service.create_job({'kind': 'diagnostics', 'export_directory': str(blocked)}, launch=False)
        with patch('backend.benchmark_diagnostics.run_diagnostics', return_value={'checked': True}):
            run_job(job['id'], self.service.runtime)
        state = self.service.get_job(job['id'])
        self.assertEqual(state['state'], 'completed')
        self.assertEqual(state['task_io']['last_export']['state'], 'failed')
        self.assertFalse(state['export_pending'])

    def test_http_rename_export_and_directory_selection(self):
        import threading
        from urllib.request import Request, urlopen
        from backend.server import make_server
        job_id, folder = self.completed()
        server = make_server('127.0.0.1', 0, self.service.runtime)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def post(path, value):
            request = Request(base + path, data=json.dumps(value).encode(),
                              headers={'Content-Type': 'application/json'}, method='POST')
            with urlopen(request) as response:
                return json.load(response)
        try:
            renamed = post(f'/api/jobs/{job_id}/io', {'name': '网页命名', 'export_directory': str(self.root / '网页成果')})
            self.assertEqual(renamed['display_name'], '网页命名')
            self.assertEqual(post(f'/api/jobs/{job_id}/export', {})['state'], 'completed')
            with patch('backend.task_io.choose_directory', return_value={'path': str(self.root), 'cancelled': False}):
                self.assertEqual(post('/api/local-directory', {})['path'], str(self.root))
            request = Request(base + '/api/local-directory', data=b'{}',
                              headers={'Origin': 'https://untrusted.example'}, method='POST')
            from urllib.error import HTTPError
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()

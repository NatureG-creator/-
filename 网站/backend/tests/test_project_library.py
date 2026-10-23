import io
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.request import Request, urlopen

from backend.project_library import create_folder, import_library_file, library_file, library_list, save_task_outputs, save_uploaded_file
from backend.server import make_server


class ProjectLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = make_server('127.0.0.1', 0, self.root)
        self.folder = create_folder(self.service, {'name': 'trial'})['path']

    def tearDown(self):
        self.service.server_close()
        self.temp.cleanup()

    def test_create_save_browse_and_import_uploaded_file(self):
        upload = self.service.upload('data.csv', io.BytesIO(b'x,y\n1,2\n'), 8)
        saved = save_uploaded_file(self.service, {'upload_id': upload['id'], 'folder': self.folder})
        self.assertEqual(library_file(self.service, saved['path']).read_bytes(), b'x,y\n1,2\n')
        self.assertEqual(library_list(self.service, self.folder)['files'][0]['name'], 'data.csv')
        imported = import_library_file(self.service, {'path': saved['path']})
        self.assertEqual(imported['name'], 'data.csv')
        _, imported_path = self.service.get_upload(imported['id'])
        self.assertEqual(imported_path.read_bytes(), b'x,y\n1,2\n')

    def test_save_finished_task_with_provenance_and_reject_running_task(self):
        job_id = 'a' * 16
        output = self.root / 'jobs' / job_id / 'outputs'
        output.mkdir(parents=True)
        (output / 'result.csv').write_text('a,b\n1,2\n', encoding='utf-8')
        from backend.runner import _atomic_json
        _atomic_json(self.root / 'jobs' / job_id / 'status.json', {'id': job_id, 'kind': 'test', 'state': 'completed'})
        result = save_task_outputs(self.service, {'job_id': job_id, 'folder': self.folder, 'files': ['result.csv']})
        copied = self.root / 'project_library' / result['files'][0]['path']
        self.assertEqual(copied.read_text(encoding='utf-8'), 'a,b\n1,2\n')
        self.assertEqual((copied.with_name(copied.name + '.source.json')).is_file(), True)
        self.assertTrue((output / 'result.csv').is_file())
        with patch.object(self.service, 'get_job', return_value={'state': 'running'}):
            with self.assertRaisesRegex(ValueError, '任务结束'):
                save_task_outputs(self.service, {'job_id': job_id, 'folder': self.folder, 'files': ['result.csv']})

    def test_reject_path_traversal_and_missing_folder(self):
        with self.assertRaises(FileNotFoundError):
            library_file(self.service, '../outside.txt')
        with self.assertRaises(FileNotFoundError):
            library_list(self.service, 'missing')

    def test_duplicate_names_are_preserved_and_api_import_creates_upload(self):
        first = self.service.upload('same.csv', io.BytesIO(b'a\n1\n'), 4)
        second = self.service.upload('same.csv', io.BytesIO(b'a\n2\n'), 4)
        saved_first = save_uploaded_file(self.service, {'upload_id': first['id'], 'folder': self.folder})
        saved_second = save_uploaded_file(self.service, {'upload_id': second['id'], 'folder': self.folder})
        self.assertEqual({saved_first['name'], saved_second['name']}, {'same.csv', 'same_2.csv'})
        base = f'http://127.0.0.1:{self.service.server_port}'
        from threading import Thread
        thread = Thread(target=self.service.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(base + '/api/project-library/import',
                              data=__import__('json').dumps({'path': f'{self.folder}/same_2.csv'}).encode(),
                              headers={'Content-Type': 'application/json'}, method='POST')
            with urlopen(request) as response:
                imported = __import__('json').load(response)
            _, path = self.service.get_upload(imported['id'])
            self.assertEqual(path.read_bytes(), b'a\n2\n')
        finally:
            self.service.shutdown()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()

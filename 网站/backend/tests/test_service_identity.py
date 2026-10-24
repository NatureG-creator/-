import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('revision_launcher', ROOT / 'launch.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class ServiceIdentityTests(unittest.TestCase):
    def test_old_backend_at_same_path_is_not_reused(self):
        health = {'service': 'corrosion-research-workbench', 'site_root': str(ROOT)}
        with patch.object(launcher.urllib.request, 'urlopen',
                          return_value=io.BytesIO(json.dumps(health).encode())):
            self.assertFalse(launcher.service_at(8536))

    def test_revision_must_match_running_backend(self):
        from backend.service_identity import source_revision
        health = {'service': 'corrosion-research-workbench', 'site_root': str(ROOT),
                  'source_revision': source_revision(ROOT)}
        for revision, expected in ((health['source_revision'], True), ('older', False)):
            with self.subTest(revision=revision):
                health['source_revision'] = revision
                with patch.object(launcher.urllib.request, 'urlopen',
                                  return_value=io.BytesIO(json.dumps(health).encode())):
                    self.assertEqual(launcher.service_at(8536), expected)

    def test_existing_same_checkout_service_is_reused_after_source_update(self):
        health = {'service': 'corrosion-research-workbench', 'site_root': str(ROOT),
                  'source_revision': 'older'}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(launcher.urllib.request, 'urlopen',
                              side_effect=lambda *args, **kwargs: io.BytesIO(json.dumps(health).encode())):
                self.assertTrue(launcher.service_for_checkout(8536))
                self.assertEqual(launcher.launch(open_browser=False, preferred_port=8536,
                                                 runtime=Path(directory)),
                                 'http://127.0.0.1:8536/')

    def test_source_change_invalidates_revision_but_runtime_does_not(self):
        from backend.service_identity import source_revision
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'backend').mkdir()
            source = root / 'backend' / 'server.py'
            source.write_text('version=1\n')
            first = source_revision(root)
            (root / '.runtime').mkdir()
            (root / '.runtime' / 'status.json').write_text('{}')
            self.assertEqual(source_revision(root), first)
            source.write_text('version=2\n')
            self.assertNotEqual(source_revision(root), first)

    def test_health_reports_revision_frozen_at_startup(self):
        from backend.server import JobServer
        with tempfile.TemporaryDirectory() as directory:
            with patch('backend.server.source_revision', return_value='startup') as revision:
                server = JobServer('127.0.0.1', 0, Path(directory))
            try:
                self.assertEqual(server.source_revision, 'startup')
                revision.assert_called_once()
            finally:
                server.server_close()


if __name__ == '__main__':
    unittest.main()

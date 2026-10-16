import unittest
from pathlib import Path
from unittest.mock import patch
from backend.system_info import json_record


class StatusReadTests(unittest.TestCase):
    def test_transient_windows_sharing_violation_is_retried(self):
        with patch.object(Path,'is_file',return_value=True), patch.object(Path,'read_text',side_effect=[PermissionError(13,'busy'),PermissionError(13,'busy'),'{"state":"completed"}']) as read:
            self.assertEqual(json_record(Path('status.json'))['state'],'completed')
            self.assertEqual(read.call_count,3)

    def test_permanent_permission_error_is_not_missing_or_success(self):
        with patch.object(Path,'is_file',return_value=True),patch.object(Path,'read_text',side_effect=PermissionError(13,'denied')) as read:
            with self.assertRaises(PermissionError):json_record(Path('status.json'))
            self.assertLessEqual(read.call_count,6)

    def test_invalid_json_is_not_silently_replaced(self):
        with patch.object(Path,'is_file',return_value=True),patch.object(Path,'read_text',return_value='broken'):
            with self.assertRaises(ValueError):json_record(Path('status.json'))

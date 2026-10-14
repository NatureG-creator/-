import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from backend.checkpoint import CheckpointStore, _replace_bytes
from backend.runner import _atomic_json, _atomic_npz
from backend.scientific_outputs import export_compatibility_npz


def windows_permission(code):
    error = PermissionError(13, "temporary Windows sharing lock")
    error.winerror = code
    return error


class AtomicWriteTests(unittest.TestCase):
    def test_transient_windows_locks_retry_all_atomic_publications(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage = root / "stage.npz"
            np.savez(stage, perfect_result=np.zeros(4), perfect_parameter=np.zeros(10),
                     perfect_a=np.ones((2, 3, 4)), perfect_d=np.zeros((2, 3, 4)),
                     perfect_cl=np.zeros((2, 3)))
            writers = {
                "csv": lambda path: _replace_bytes(path, b"stage,mean\n1,2\n"),
                "json": lambda path: _atomic_json(path, {"ok": True}),
                "npz": lambda path: _atomic_npz(path, a=np.array([1, 2])),
                "best": lambda path: CheckpointStore(path.parent, "test").save_arrays(a=np.array([1])),
                "compatibility": lambda path: export_compatibility_npz(path, [stage]),
            }
            original_replace = os.replace
            for code in (5, 32, 33):
                for name, writer in writers.items():
                    with self.subTest(winerror=code, publication=name):
                        calls = []
                        def replace(source, destination):
                            calls.append((source, destination))
                            if len(calls) <= 2:
                                raise windows_permission(code)
                            original_replace(source, destination)
                        path = root / f"{name}_{code}" / "result"
                        path.parent.mkdir()
                        with patch("backend.checkpoint.os.replace", side_effect=replace):
                            with patch("time.sleep") as sleep:
                                writer(path)
                        self.assertEqual(len(calls), 3)
                        self.assertEqual(sleep.call_count, 2)
                        self.assertTrue(Path(calls[-1][1]).is_file())
                        self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_permanent_windows_lock_is_bounded_preserves_old_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.csv"
            path.write_bytes(b"old")
            with patch("backend.checkpoint.os.replace", side_effect=windows_permission(5)) as replace:
                with patch("time.sleep") as sleep:
                    with self.assertRaises(PermissionError):
                        _replace_bytes(path, b"new")
            self.assertGreater(replace.call_count, 1, "短暂共享锁必须给出恢复机会")
            self.assertLessEqual(replace.call_count, 10, "永久权限错误必须有界退出")
            self.assertEqual(sleep.call_count, replace.call_count - 1)
            self.assertEqual(path.read_bytes(), b"old")
            self.assertFalse(list(Path(folder).glob("*.tmp")))

    def test_unrelated_permission_error_is_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.csv"
            with patch("backend.checkpoint.os.replace", side_effect=windows_permission(2)) as replace:
                with patch("time.sleep") as sleep:
                    with self.assertRaises(PermissionError):
                        _replace_bytes(path, b"new")
            self.assertEqual(replace.call_count, 1)
            sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()

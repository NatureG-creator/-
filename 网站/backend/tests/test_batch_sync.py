import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.config import default_simulation_config
from backend.server import make_server
from backend.git_sync import sync_website


class BatchTests(unittest.TestCase):
    def test_changed_second_upload_leaves_no_published_jobs(self):
        import io
        import numpy as np
        from scipy.io import savemat
        with tempfile.TemporaryDirectory() as folder:
            server = make_server("127.0.0.1", 0, Path(folder))
            try:
                stream = io.BytesIO()
                savemat(stream, {"target_data": np.asarray([[10, 2, 1, 3, .2, .3]])})
                content = stream.getvalue()
                uploaded = server.upload("targets.mat", io.BytesIO(content), len(content))
                _, path = server.get_upload(uploaded["id"])
                with path.open("ab") as output:
                    output.write(b"changed")
                with self.assertRaisesRegex(ValueError, "修改"):
                    server.create_batch({"config": default_simulation_config(), "run_mode": "sequential",
                        "cases": [{"case_name": "first", "targets": [[10, 2, 1, 3, .2, .3]]},
                                  {"case_name": "second", "upload_id": uploaded["id"]}]})
                self.assertEqual(list((Path(folder) / "jobs").iterdir()), [])
                self.assertFalse(server.pending_jobs)
            finally:
                server.server_close()

    def test_all_cases_validate_before_any_task_is_created(self):
        with tempfile.TemporaryDirectory() as folder:
            server = make_server("127.0.0.1", 0, Path(folder))
            try:
                config = default_simulation_config()
                with patch.object(server, "launch") as launch:
                    with self.assertRaises(ValueError):
                        server.create_batch({"config": config, "run_mode": "sequential",
                            "cases": [{"case_name": "valid", "targets": [[10, 2, 1, 3, .2, .3]]},
                                      {"case_name": "bad", "targets": [[1, 2]]}]})
                self.assertEqual(list((Path(folder) / "jobs").iterdir()), [])
                launch.assert_not_called()
            finally:
                server.server_close()

    def test_mixed_mode_does_not_silently_drop_disabled_cases(self):
        with tempfile.TemporaryDirectory() as folder:
            server = make_server("127.0.0.1", 0, Path(folder))
            try:
                with self.assertRaisesRegex(ValueError, "关闭"):
                    server.create_batch({"config": default_simulation_config(), "run_mode": "mixed",
                        "sequential_enabled": False, "parallel_enabled": True,
                        "cases": [{"case_name": "case", "mode": "sequential",
                                   "targets": [[10, 2, 1, 3, .2, .3]]}]})
            finally:
                server.server_close()


class GitSyncTests(unittest.TestCase):
    def test_sync_preserves_partially_staged_website_file(self):
        def fake_git(*args, **kwargs):
            if args[:3] == ("diff", "--cached", "--name-only"):
                return "网站/frontend/app.js"
            if args[:2] == ("diff", "--name-only"):
                return "网站/frontend/app.js"
            return ""
        with patch("backend.git_sync.sync_status", return_value={
            "available": True, "branch": "main", "directory": "网站", "remote": "https://github.com/example/repo"
        }), patch("backend.git_sync._git", side_effect=fake_git) as git:
            with self.assertRaisesRegex(ValueError, "部分暂存"):
                sync_website()
        self.assertFalse(any(call.args[:1] == ("add",) for call in git.call_args_list))

    def test_sync_refuses_unrelated_staged_files(self):
        with patch("backend.git_sync.sync_status", return_value={
            "available": True, "branch": "main", "directory": "网站", "remote": "https://github.com/example/repo"
        }), patch("backend.git_sync._git", return_value="private-data.csv") as git:
            with self.assertRaisesRegex(ValueError, "之外"):
                sync_website()
        self.assertEqual(git.call_args_list[0].args, ("diff", "--cached", "--name-only", "-z"))
        self.assertEqual(git.call_count, 1)

    def test_sync_pushes_pending_commit_when_no_new_changes(self):
        def fake_git(*args, **kwargs):
            return "123abc" if args == ("rev-parse", "HEAD") else ""
        with patch("backend.git_sync.sync_status", return_value={
            "available": True, "branch": "main", "directory": "网站", "remote": "https://github.com/example/repo"
        }), patch("backend.git_sync._git", side_effect=fake_git) as git:
            result = sync_website()
        self.assertFalse(result["committed"])
        self.assertTrue(result["success"])
        self.assertTrue(any(call.args[:1] == ("push",) for call in git.call_args_list))
        self.assertTrue(any(call.args == ("add", "--", ":(top)网站") for call in git.call_args_list))


if __name__ == "__main__":
    unittest.main()

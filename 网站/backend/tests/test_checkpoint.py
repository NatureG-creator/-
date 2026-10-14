import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from backend.checkpoint import CheckpointStore


class CheckpointTests(unittest.TestCase):
    def test_round_trip_and_config_fingerprint(self):
        with tempfile.TemporaryDirectory() as folder:
            store = CheckpointStore(Path(folder), "abc123")
            state = {"stage": 1, "generation": 2, "next_individual": 3, "chrom": [[0, 1]], "rng_state": {"x": 7}}
            store.save(state)
            self.assertEqual(store.load(), state)
            with self.assertRaisesRegex(ValueError, "配置"):
                CheckpointStore(Path(folder), "different").load()

    def test_corrupted_current_falls_back_to_previous(self):
        with tempfile.TemporaryDirectory() as folder:
            store = CheckpointStore(Path(folder), "same")
            store.save({"generation": 1})
            store.save({"generation": 2})
            store.path.write_text("{truncated", encoding="utf-8")
            self.assertEqual(store.load(), {"generation": 1})

    def test_best_arrays_are_immutable_and_transaction_references_match(self):
        with tempfile.TemporaryDirectory() as folder:
            store = CheckpointStore(Path(folder), "same")
            self.assertTrue(hasattr(store, "save_arrays"), "需要不可变最优状态接口")
            first = store.save_arrays(a=np.array([1]), d=np.array([2]), cl=np.array([3]))
            store.save({"best_state": first, "generation": 1})
            second = store.save_arrays(a=np.array([9]), d=np.array([8]), cl=np.array([7]))
            # 最优文件已写，元数据替换尚未发生时中断。
            self.assertEqual(store.load()["best_state"], first)
            np.testing.assert_array_equal(store.load_arrays(first)["a"], [1])
            store.save({"best_state": second, "generation": 2})
            (Path(folder) / second["file"]).write_bytes(b"broken")
            self.assertEqual(store.load()["best_state"], first)

    def test_environment_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIn("engine_fingerprint", __import__("inspect").signature(CheckpointStore).parameters)
            CheckpointStore(Path(folder), "same", engine_fingerprint="old").save({"generation": 1})
            with self.assertRaisesRegex(ValueError, "引擎|环境"):
                CheckpointStore(Path(folder), "same", engine_fingerprint="new").load()

    def test_fallback_commit_does_not_replace_valid_previous_with_corrupt_best(self):
        with tempfile.TemporaryDirectory() as folder:
            store = CheckpointStore(Path(folder), "same")
            first = store.save_arrays(a=np.array([1]))
            store.save({"best_state": first, "generation": 1})
            second = store.save_arrays(a=np.array([2]))
            store.save({"best_state": second, "generation": 2})
            (Path(folder) / second["file"]).write_bytes(b"bad")
            self.assertEqual(store.load()["generation"], 1)
            store.save({"best_state": first, "generation": 3})
            store.path.write_bytes(b"{bad")
            self.assertEqual(store.load()["generation"], 1)

    def test_previous_best_snapshot_survives_many_small_progress_commits(self):
        with tempfile.TemporaryDirectory() as folder:
            store = CheckpointStore(Path(folder), "same")
            first = store.save_arrays(a=np.array([1]))
            store.save({"best_state": first, "generation": 1})
            second = store.save_arrays(a=np.array([2]))
            store.save({"best_state": second, "generation": 2})
            store.save({"best_state": second, "generation": 3})
            store.save({"best_state": second, "generation": 4})
            (Path(folder) / second["file"]).write_bytes(b"bad")
            self.assertEqual(store.load()["best_state"], first)
            np.testing.assert_array_equal(store.load_arrays(first)["a"], [1])

    def test_valid_json_with_invalid_top_level_rolls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            store = CheckpointStore(Path(folder), "same")
            store.save({"generation": 1})
            store.save({"generation": 2})
            store.path.write_text("[]", encoding="utf-8")
            self.assertEqual(store.load()["generation"], 1)


if __name__ == "__main__":
    unittest.main()

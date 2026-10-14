import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()

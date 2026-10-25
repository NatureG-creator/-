import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.engine_releases import activate, binding, freeze_binding, launch_profile, precheck_bound_job, worker_root


class EngineReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.runtime = Path(temporary.name)
        self.root = self.runtime / "original"
        self.root.mkdir()
        release = self.runtime / "engine_releases/numba-test"
        (release / "site/engine").mkdir(parents=True)
        source = release / "site/engine/kernel.py"
        source.write_text("value = 1\n", encoding="utf-8")
        interpreter = release / ("venv/Scripts/python.exe" if os.name == "nt" else "venv/bin/python")
        interpreter.parent.mkdir(parents=True)
        interpreter.write_bytes(b"test")
        self.manifest = release / "manifest.json"
        self.manifest.write_text(json.dumps({"release_id": "numba-test", "label": "Numba test",
            "files": {"engine/kernel.py": hashlib.sha256(source.read_bytes()).hexdigest()}}), encoding="utf-8")
        self.source = source

    def job(self, name):
        folder = self.runtime / "jobs" / name
        folder.mkdir(parents=True)
        return folder

    def test_existing_jobs_without_binding_keep_original_after_activation(self):
        old = self.job("old")
        activate(self.runtime, self.root, "numba-test")
        self.assertEqual(binding(old)["release_id"], "original")
        self.assertEqual(Path(launch_profile(old, self.runtime, self.root)["root"]), self.root)

    def test_rollback_affects_new_jobs_only(self):
        spec = {"kind": "simulation", "config": {"mode": "pycharm"}}
        activate(self.runtime, self.root, "numba-test")
        accelerated = self.job("accelerated")
        freeze_binding(accelerated, spec, self.runtime, self.root)
        activate(self.runtime, self.root, "original")
        new = self.job("new")
        freeze_binding(new, spec, self.runtime, self.root)
        self.assertEqual(binding(accelerated)["release_id"], "numba-test")
        self.assertEqual(binding(new)["release_id"], "original")
        self.assertEqual(worker_root(accelerated, self.runtime, self.root), self.source.parents[1])
        with self.assertRaisesRegex(ValueError, "已经冻结"):
            freeze_binding(accelerated, spec, self.runtime, self.root)

    def test_unvalidated_modes_keep_original(self):
        activate(self.runtime, self.root, "numba-test")
        for mode in ("strict", "fast"):
            job = self.job(mode)
            freeze_binding(job, {"kind": "simulation", "config": {"mode": mode}}, self.runtime, self.root)
            self.assertEqual(binding(job)["release_id"], "original")

    def test_explicit_dropdown_choice_overrides_global_default(self):
        spec = {"kind": "simulation", "config": {"mode": "pycharm"}}
        activate(self.runtime, self.root, "numba-test")
        original = self.job("explicit-original")
        freeze_binding(original, {**spec, "engine_release": "original"}, self.runtime, self.root)
        self.assertEqual(binding(original)["release_id"], "original")
        activate(self.runtime, self.root, "original")
        accelerated = self.job("explicit-numba")
        freeze_binding(accelerated, {**spec, "engine_release": "numba-test"}, self.runtime, self.root)
        self.assertEqual(binding(accelerated)["release_id"], "numba-test")

    def test_explicit_numba_rejects_non_cpu_modes(self):
        for mode in ("strict", "fast"):
            with self.assertRaisesRegex(ValueError, "只支持"):
                freeze_binding(self.job("invalid-" + mode), {"kind": "simulation",
                    "config": {"mode": mode}, "engine_release": "numba-test"}, self.runtime, self.root)

    def test_batch_and_job_spec_preserve_explicit_engine_choice(self):
        from backend.config import website_default_simulation_config
        from backend.server import make_server
        server = make_server("127.0.0.1", 0, self.runtime)
        self.addCleanup(server.server_close)
        for release_id in ("numba-test", "original"):
            with patch("backend.batch_service.threading.Thread.start"):
                batch = server.create_batch({"config": website_default_simulation_config(),
                    "engine_release": release_id, "run_mode": "single", "cases": [
                        {"case_name": "engine choice", "targets": [[10, 2, 1, 3, .2, .3]]}]})
            folder = self.runtime / "jobs" / batch["jobs"][0]["id"]
            self.assertEqual(binding(folder)["release_id"], release_id)
            self.assertEqual(json.loads((folder / "spec.json").read_text(encoding="utf-8"))["engine_release"], release_id)

    def test_tampered_release_never_silently_falls_back(self):
        activate(self.runtime, self.root, "numba-test")
        job = self.job("tampered")
        freeze_binding(job, {"kind": "simulation", "config": {"mode": "pycharm"}}, self.runtime, self.root)
        self.source.write_text("value = 2\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "引擎文件已改变"):
            launch_profile(job, self.runtime, self.root)

    def test_original_precheck_uses_original_runner(self):
        old = self.job("legacy")
        with patch("backend.runner.precheck_resume", return_value={"available": True}) as checked:
            self.assertEqual(precheck_bound_job({}, old, self.runtime, self.root), {"available": True})
            checked.assert_called_once_with({}, old)


if __name__ == "__main__":
    unittest.main()

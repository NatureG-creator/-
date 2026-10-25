import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("desktop_site_launch", ROOT / "launch.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class DesktopLaunchTests(unittest.TestCase):
    def test_default_runtime_is_used_when_no_runtime_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "website-data"
            with patch.object(launcher, "DEFAULT_RUNTIME", runtime), \
                 patch.object(launcher, "service_for_checkout", return_value=True) as health:
                url = launcher.launch(open_browser=False, preferred_port=8534)
            self.assertEqual(url, "http://127.0.0.1:8534/")
            self.assertTrue(runtime.is_dir())
            health.assert_called_once_with(8534)

    def test_reuses_service_marker_from_selected_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            (runtime / "service.json").write_text(json.dumps({"port": 8536}))
            with patch.object(launcher, "service_for_checkout", return_value=True) as health:
                url = launcher.launch(open_browser=False, preferred_port=8534, runtime=runtime, fixed_port=False)
            self.assertEqual(url, "http://127.0.0.1:8536/")
            health.assert_called_once_with(8536)

    def test_new_server_receives_selected_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            with patch.object(launcher, "service_for_checkout", return_value=False), \
                 patch.object(launcher, "service_at", return_value=True), \
                 patch.object(launcher.importlib.util, "find_spec", return_value=object()), \
                 patch.object(launcher.socket, "socket"), \
                 patch.object(launcher.subprocess, "Popen") as process:
                launcher.launch(open_browser=False, preferred_port=8536, runtime=runtime)
            command = process.call_args.args[0]
            self.assertEqual(command[-2:], ["--runtime", str(runtime)])
            self.assertEqual(command[2], str(ROOT / "start_server.py"))
            environment = process.call_args.kwargs["env"]
            self.assertEqual(environment["TEMP"], str(runtime / "temp"))
            self.assertEqual(environment["TMP"], str(runtime / "temp"))
            self.assertTrue((runtime / "temp").is_dir())


if __name__ == "__main__":
    unittest.main()

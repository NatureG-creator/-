import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from backend.server import make_server


class ServerTests(unittest.TestCase):
    def test_defaults_and_pointcloud_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            server = make_server("127.0.0.1", 0, Path(folder))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urllib.request.urlopen(base + "/api/defaults") as response:
                    defaults = json.load(response)
                self.assertIn("STAGE_GA_CONFIG", defaults["simulation"])
                upload = urllib.request.Request(base + "/api/uploads?name=scan.xyz", method="POST",
                                                data=b"0 0 1\n5 0 2\n0 7 3\n")
                with urllib.request.urlopen(upload) as response:
                    record = json.load(response)
                with urllib.request.urlopen(base + "/api/uploads/" + record["id"] + "/inspect?kind=pointcloud") as response:
                    inspected = json.load(response)
                self.assertEqual(inspected["size_mm"], [5.0, 7.0])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()

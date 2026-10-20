import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.git_sync import _repository_context


class RepositoryContextTests(unittest.TestCase):
    def test_standalone_site_uses_configured_repository(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            site = root / "standalone-site"
            repo = root / "repo"
            site.mkdir()
            (repo / ".git").mkdir(parents=True)
            (repo / site.name).mkdir()
            with patch("backend.git_sync.ROOT", site), patch.dict(
                    os.environ, {"CORROSION_GIT_ROOT": str(repo)}, clear=False):
                self.assertEqual(_repository_context(), (repo, site.name))


if __name__ == "__main__":
    unittest.main()

"""Identify the source loaded by a local website service, excluding research data."""

import hashlib
from pathlib import Path


def source_revision(root: Path) -> str:
    root = Path(root)
    files = list(root.glob('*.py'))
    files.extend((root / 'backend').glob('*.py'))
    files.extend(path for path in (root / 'frontend').rglob('*')
                 if path.is_file() and path.suffix in {'.js', '.mjs', '.html', '.css'}
                 and 'tests' not in path.relative_to(root / 'frontend').parts
                 and not path.name.endswith('.test.mjs'))
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode('utf-8') + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()

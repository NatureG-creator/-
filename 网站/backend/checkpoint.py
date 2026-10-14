"""Atomic, configuration-bound progress records."""

from __future__ import annotations

import json
import os
from pathlib import Path


class CheckpointStore:
    def __init__(self, folder: Path, fingerprint: str):
        self.folder = Path(folder)
        self.fingerprint = fingerprint
        self.path = self.folder / "progress.json"

    def save(self, state: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump({"fingerprint": self.fingerprint, "state": state}, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        record = json.loads(self.path.read_text(encoding="utf-8"))
        if record.get("fingerprint") != self.fingerprint:
            raise ValueError("检查点配置与当前任务配置不一致")
        return record["state"]

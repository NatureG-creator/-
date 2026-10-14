"""Versioned transactions: immutable large states and two small progress records."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import time
import uuid
from pathlib import Path

import numpy as np
import scipy

CHECKPOINT_VERSION = 2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def engine_environment_fingerprint() -> str:
    """Bind exact copied engine and persistence logic to the numerical environment."""
    root = Path(__file__).resolve().parents[1]
    sources = sorted((root / "engine").rglob("*.py"))
    sources += [Path(__file__).with_name(name) for name in
                ("checkpoint.py", "strict_ga.py", "scientific_outputs.py", "runner.py")]
    digest = hashlib.sha256()
    for path in sources:
        if path.is_file():
            digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
            digest.update(path.read_bytes())
    environment = {"python": platform.python_version(), "implementation": platform.python_implementation(),
                   "system": platform.platform(), "machine": platform.machine(),
                   "processor": platform.processor(),
                   "numpy": np.__version__, "scipy": scipy.__version__,
                   "scikit_image": importlib.metadata.version("scikit-image"),
                   "thread_environment": {key: os.environ.get(key) for key in
                                          ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")}}
    digest.update(json.dumps(environment, sort_keys=True).encode())
    return digest.hexdigest()


def _state_hash(state: dict) -> str:
    return hashlib.sha256(json.dumps(state, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _atomic_replace(source: Path, destination: Path) -> None:
    """Retry transient Windows sharing failures without consuming scientific RNG.

    Ten attempts wait at most 1.375 seconds in total. A permanent denial and
    errors other than Windows access/sharing/lock violations still propagate.
    """
    for attempt in range(10):
        try:
            os.replace(source, destination)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == 9:
                raise
            time.sleep(min(0.025 * 2 ** attempt, 0.2))


def _replace_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        _atomic_replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class CheckpointStore:
    def __init__(self, folder: Path, fingerprint: str, *, engine_fingerprint: str | None = None):
        self.folder = Path(folder)
        self.fingerprint = fingerprint
        self.engine_fingerprint = engine_fingerprint or engine_environment_fingerprint()
        self.path = self.folder / "progress.json"
        self.previous_path = self.folder / "progress.previous.json"
        self.previous_best_path = self.folder / "progress.best.previous.json"
        self.recovered_from_previous = False
        self.recovery_source = None

    def _validate(self, record: dict, *, verify_arrays: bool = True) -> dict:
        if not isinstance(record, dict):
            raise OSError("检查点元数据不是对象")
        if record.get("fingerprint") != self.fingerprint:
            raise ValueError("检查点配置与当前任务配置不一致")
        if record.get("version") != CHECKPOINT_VERSION:
            raise ValueError("旧版检查点缺少原子状态引用，不能保证一致性；请创建新任务")
        if record.get("engine_fingerprint") != self.engine_fingerprint:
            raise ValueError("检查点引擎或 Python/NumPy/SciPy 环境与当前任务不一致；请创建新任务")
        state = record["state"]
        if not isinstance(state, dict):
            raise OSError("检查点状态不是对象")
        if _state_hash(state) != record["state_sha256"]:
            raise OSError("检查点元数据校验失败")
        if verify_arrays and state.get("best_state"):
            self._validate_array_ref(state["best_state"])
        return state

    def _validate_array_ref(self, reference: dict) -> Path:
        name = reference["file"]
        if Path(name).name != name or not name.startswith("best_") or not name.endswith(".npz"):
            raise OSError("检查点状态路径不合法")
        path = self.folder / name
        if not path.is_file() or sha256_file(path) != reference["sha256"]:
            raise OSError("检查点最优状态文件丢失或损坏")
        return path

    def save_arrays(self, **arrays) -> dict:
        """Write large arrays before publishing their reference in progress.json."""
        self.folder.mkdir(parents=True, exist_ok=True)
        temporary = self.folder / ("best_" + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("wb") as stream:
                np.savez_compressed(stream, **arrays)
                stream.flush()
                os.fsync(stream.fileno())
            digest = sha256_file(temporary)
            path = self.folder / f"best_{digest}.npz"
            if path.exists() and sha256_file(path) == digest:
                temporary.unlink()
            else:
                _atomic_replace(temporary, path)
            return {"file": path.name, "sha256": digest}
        finally:
            temporary.unlink(missing_ok=True)

    def load_arrays(self, reference: dict) -> dict:
        path = self._validate_array_ref(reference)
        with np.load(path, allow_pickle=False) as arrays:
            return {name: arrays[name].copy() for name in arrays.files}

    def save(self, state: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        # Preserve the last intact transaction before replacing current. A corrupt
        # current after a fallback must not overwrite the intact previous record.
        if self.path.exists() and not self.recovered_from_previous:
            content = self.path.read_bytes()
            try:
                previous_state = self._validate(json.loads(content), verify_arrays=False)
            except (OSError, KeyError, json.JSONDecodeError):
                pass
            else:
                if (previous_state.get("best_state") and
                        previous_state.get("best_state") != state.get("best_state")):
                    _replace_bytes(self.previous_best_path, content)
                _replace_bytes(self.previous_path, content)
        record = {"version": CHECKPOINT_VERSION, "fingerprint": self.fingerprint,
                  "engine_fingerprint": self.engine_fingerprint,
                  "state_sha256": _state_hash(state), "state": state}
        _replace_bytes(self.path, json.dumps(record, ensure_ascii=False,
                                            allow_nan=False).encode("utf-8"))
        self.recovered_from_previous = False
        self._prune_arrays()

    def _prune_arrays(self) -> None:
        # Only current and previous best states are needed. Orphans from a crash
        # before publishing a reference can be discarded after the next commit.
        keep = set()
        for path in (self.path, self.previous_path, self.previous_best_path):
            if path.is_file():
                try:
                    state = json.loads(path.read_bytes())["state"]
                    if state.get("best_state"):
                        keep.add(state["best_state"]["file"])
                except (KeyError, TypeError, json.JSONDecodeError):
                    return
        for path in self.folder.glob("best_*.npz"):
            if path.name not in keep:
                try:
                    path.unlink()
                except OSError:
                    pass

    def load(self) -> dict | None:
        errors = []
        for index, path in enumerate((self.path, self.previous_path, self.previous_best_path)):
            if not path.exists():
                continue
            try:
                state = self._validate(json.loads(path.read_bytes()))
            except ValueError as exc:
                if isinstance(exc, json.JSONDecodeError):
                    errors.append(str(exc))
                    continue
                raise
            except (OSError, KeyError, TypeError) as exc:
                errors.append(str(exc))
                continue
            self.recovered_from_previous = index > 0
            self.recovery_source = path.name
            return state
        if errors:
            raise ValueError("所有保留检查点均不可恢复：" + "；".join(errors))
        return None


def precheck_checkpoint(folder: Path, fingerprint: str, *,
                        engine_fingerprint: str | None = None) -> dict:
    """Read-only validation; incompatible/corrupt records raise ValueError."""
    store = CheckpointStore(folder, fingerprint, engine_fingerprint=engine_fingerprint)
    state = store.load()
    return {"available": state is not None, "version": CHECKPOINT_VERSION,
            "recovered_from_previous": store.recovered_from_previous,
            "recovery_source": store.recovery_source,
            "generation": None if state is None else state.get("generation"),
            "completed_individuals": 0 if state is None else state.get("next_individual", 0),
            "completed": False if state is None else state.get("completed", False)}

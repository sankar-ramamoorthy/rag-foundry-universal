# llm_service/src/core/model_policy.py
"""
WP-M7: runtime-persisted model policy -- which concrete model is active
for each named "slot" (default, fast, smart, reasoning, ...), stored
outside git so it survives a redeploy/rebuild without ever touching
models.yaml. A slot is an OVERRIDE: an absent file or an absent slot
falls back to whatever models.yaml already defines for that alias.

Concurrency: the on-disk write itself is atomic (write to a `.tmp` file,
then os.replace/Path.replace, which is an atomic rename on POSIX
regardless of process count) so a concurrent reader never observes a
torn file. The read-modify-write section (load -> merge one slot ->
save) is additionally guarded by a real cross-process filesystem lock
(fcntl.flock on a sidecar `.lock` file) rather than threading.Lock,
because threading.Lock only protects concurrent threads inside ONE
Python process and gives no protection at all if llm_service is ever
run with multiple Uvicorn worker processes.

Scope: this locking scheme is single-host/local-filesystem only -- fine
for the current single-instance deployment. If llm_service is ever
horizontally scaled across multiple hosts sharing one policy file, this
scheme would need a real distributed lock; that's out of scope here and
deliberately not silently assumed away.
"""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

try:
    import fcntl  # POSIX only -- this service only ever runs on Linux
except ImportError:  # pragma: no cover - Windows dev machines
    fcntl = None  # type: ignore[assignment]

POLICY_VERSION = 1


class ModelPolicyError(ValueError):
    """Raised when the policy file exists but cannot be parsed."""


def _policy_path() -> Path:
    return Path(os.getenv("MODEL_POLICY_PATH", "/runtime/model-policy.json"))


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    """Cross-process advisory lock on a sidecar `<path>.lock` file. A
    no-op on platforms without fcntl (e.g. local Windows dev) -- the
    atomic rename in write_slot()/clear_slot() is still safe there for a
    single process; it's only concurrent OS processes that need flock."""
    if fcntl is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with open(lock_path, "a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_raw(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"version": POLICY_VERSION, "slots": {}}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ModelPolicyError(f"corrupt model policy file at {path}: {e}") from e
    if not isinstance(loaded, dict) or not isinstance(loaded.get("slots"), dict):
        raise ModelPolicyError(f"malformed model policy file at {path}")
    return loaded


def _write_raw(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        Path(tmp_name).replace(path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def load_policy() -> Dict[str, Any]:
    """Missing file -> empty defaults. Corrupt JSON -> ModelPolicyError
    (the caller, ModelRegistry.get_registry(), degrades that to
    yaml-only aliases rather than crashing)."""
    return _read_raw(_policy_path())


def write_slot(
    slot: str, model: str, *, updated_by: Optional[str] = None
) -> Dict[str, Any]:
    path = _policy_path()
    with _locked(path):
        data = _read_raw(path)
        data["version"] = POLICY_VERSION
        data["slots"][slot] = {
            "model": model,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by,
        }
        _write_raw(path, data)
        return data


def clear_slot(slot: str) -> Dict[str, Any]:
    path = _policy_path()
    with _locked(path):
        data = _read_raw(path)
        data["version"] = POLICY_VERSION
        data["slots"].pop(slot, None)
        _write_raw(path, data)
        return data

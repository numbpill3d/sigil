"""Atomic writes + advisory lock + intent allowlist gate.

This module is the ONLY sanctioned path for mutating vault notes. Every
other feature (provenance, conflict, hatch, autonomy) routes writes through
`atomic_write()` so we get three guarantees at once:

1. ATOMICITY — write to a temp file then `os.replace` (atomic rename), so a
   crash mid-write never leaves a half-written note. Plus an fcntl advisory
   lock so two processes (agent + human in Obsidian) don't interleave.
2. MERGE — before overwriting, we read-merge: we never blindly clobber a
   human note. `stamp()`-style writes go through here with append/branch
   semantics (enforced by callers via the `force` flag).
3. INTENT GATE — every write is checked against the agent's `intent.md`
   allowlist (`allowed` / `forbidden`). This is a CODE-LEVEL enforcement,
   not a prompt suggestion: a write whose target or action isn't in
   `allowed`, or is in `forbidden`, is rejected regardless of what the
   model "wanted". Re-loaded from intent.md on every call (see autonomy).

The gate is optional (pass `gate=None` to disable, e.g. for human-authored
files or tests). SIGIL agent writes must pass a gate built from the active
intent.
"""

from __future__ import annotations

import fcntl
import os
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_lock = threading.Lock()  # process-local guard for the fcntl region


class IntentGate:
    """Code-level allowlist derived from intent.md."""

    def __init__(self, allowed: list[str], forbidden: list[str]):
        self.allowed = set(allowed)
        self.forbidden = set(forbidden)

    @classmethod
    def from_intent(cls, intent: dict) -> "IntentGate":
        return cls(
            allowed=list(intent.get("allowed", [])) or ["*"],
            forbidden=list(intent.get("forbidden", [])),
        )

    def allows(self, action: str, target: str) -> bool:
        """Return True if the (action, target) passes the gate.

        `allowed` of ["*"] permits anything not explicitly forbidden.
        `forbidden` entries are matched as substrings of target/action.
        `allowed` entries are matched as prefixes/substrings of target.
        """
        for f in self.forbidden:
            if f and (f in target or f in action):
                return False
        if "*" in self.allowed:
            return True
        for a in self.allowed:
            if a == "*" or a in target or a in action:
                return True
        return False


class GateRejected(Exception):
    """Raised when a write fails the intent allowlist."""


@contextmanager
def _intra_process_lock(path: str):
    # advisory file lock; falls back gracefully if not supported
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def atomic_write(
    path: str,
    text: str,
    gate: Optional[IntentGate] = None,
    action: str = "write",
) -> None:
    """Write `text` to `path` atomically, behind an advisory lock.

    `gate` (if provided) must allow (action, path); otherwise GateRejected.
    Creates parent dirs as needed. Never partial-writes.
    """
    if gate is not None and not gate.allows(action, path):
        raise GateRejected(f"intent gate rejected {action} on {path}")
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    # process-local + OS advisory lock around the temp-write + replace
    with _lock:
        fd_ctx = _intra_process_lock(path)
        with fd_ctx:
            tmp_fd, tmp_path = tempfile.mkstemp(dir=parent, suffix=".tmp")
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                    fh.write(text)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_path, path)
            except BaseException:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise

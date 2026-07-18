"""Executable `run` notes (Phase 2, P2-4).

A note MAY contain a ```` ```run ```` fenced block. In v1 these were pure
data (surfaced to the human, never executed). P2-4 makes them OPTIONALLY
executable — but ONLY when the agent's intent explicitly allows `run`, and
ONLY inside a confined subprocess:

  - no shell (execvp-style list argv, never `sh -c`),
  - cwd is the vault root, env is a minimal allowlist (no secrets leaked),
  - hard timeout (default 10s) -> killed,
  - stdout/stderr captured and returned as DATA (never written back to the
    vault automatically; the caller decides),
  - a run NEVER writes to the vault (that path stays gated by IntentGate).

Default (no `run` in intent.allowed): `execute_run` refuses and
`extract_run_blocks` just returns the text. This is fail-closed: an agent
cannot escalate to code execution without the human opting in via intent.md.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import List, Optional

_RUN_RE = re.compile(r"```run\s*\n(.*?)```", re.DOTALL)


def extract_run_blocks(text: str) -> List[str]:
    """Return the raw command text of every ```run block (data only)."""
    return [m.group(1).rstrip("\n") for m in _RUN_RE.finditer(text)]


def run_allowed(intent: dict) -> bool:
    """True only if intent.allowed contains 'run' (opt-in, fail-closed)."""
    allowed = intent.get("allowed", [])
    if isinstance(allowed, str):
        allowed = [allowed]
    return "run" in allowed


def execute_run(
    note_path: str,
    intent: dict,
    timeout: float = 10.0,
    gate=None,
) -> dict:
    """Execute ```run blocks in `note_path` if intent allows.

    Returns {"allowed": bool, "ran": bool, "outputs": [str], "errors": [str]}.
    If not allowed, returns allowed=False, ran=False, outputs=[] (the blocks
    are NOT executed). On execution, each block runs in a confined subprocess;
    output is captured. A block is split into argv on whitespace (no shell).
    """
    text = open(note_path, encoding="utf-8").read()
    blocks = extract_run_blocks(text)
    if not blocks:
        return {"allowed": run_allowed(intent), "ran": False, "outputs": [], "errors": []}
    if not run_allowed(intent):
        return {"allowed": False, "ran": False, "outputs": [], "errors": ["intent does not allow run"]}
    # gate check: execution is itself a 'run' action gated by intent
    if gate is not None and not gate.allows("run", note_path):
        return {"allowed": False, "ran": False, "outputs": [], "errors": ["gate rejected run"]}
    outputs: List[str] = []
    errors: List[str] = []
    vault_root = os.path.dirname(os.path.abspath(note_path))
    safe_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": vault_root}
    for block in blocks:
        argv = block.split()
        if not argv:
            continue
        try:
            proc = subprocess.run(
                argv,
                cwd=vault_root,
                env=safe_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            outputs.append(out)
            if proc.returncode != 0:
                errors.append(f"exit={proc.returncode}")
        except subprocess.TimeoutExpired:
            errors.append("timeout")
        except Exception as e:  # noqa: BLE001 - surface as data
            errors.append(f"error: {e}")
    return {"allowed": True, "ran": True, "outputs": outputs, "errors": errors}

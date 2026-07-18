"""Sandbox boundary (Phase 2, P2-2).

The `delegate` autonomy tier lets an agent spawn sub-agents. That is a real
escalation: a sub-agent must NOT be able to write anywhere outside its
confined area or execute unconfined code. This module is the boundary that
makes `delegate` safe to enable.

`Sandbox(vault_root)`:
  - `confined(p)`: True only if `p` resolves under `<vault>/delegates/`
    (the ONLY place a delegate may write). Anything else is rejected.
  - `spawn(name, brief, gate)`: writes `<vault>/delegates/<name>.md` via the
    gated atomic_write path (so intent still applies) and returns its path.
  - delegates inherit NO shell/exec by default; they are notes, not processes.

The `delegate` tier in autonomy.py returns "ask" unless intent.allowed
contains "delegate" AND a Sandbox is in play — fail-closed.
"""

from __future__ import annotations

import os
from typing import Optional

from . import lock
from .frontmatter import emit


class Sandbox:
    """Confines delegate writes to <vault>/delegates/ and nowhere else."""

    def __init__(self, vault_root: str):
        self.vault_root = os.path.realpath(vault_root)
        self.dir = os.path.join(self.vault_root, "delegates")

    def confined(self, path: str) -> bool:
        """True iff `path` stays under the delegates dir."""
        rp = os.path.realpath(path)
        return rp == self.dir or rp.startswith(self.dir + os.sep)

    def spawn(self, name: str, brief: str, gate=None) -> str:
        """Create a delegate note under delegates/, gated. Returns its path.

        Confinement to the delegates dir IS the security boundary here; the
        optional `gate` (intent) is checked in addition if provided, but the
        sandbox confinement always applies regardless.
        """
        os.makedirs(self.dir, exist_ok=True)
        path = os.path.join(self.dir, f"{name}.md")
        if not self.confined(path):
            raise PermissionError(f"delegate write escapes sandbox: {path}")
        text = emit(
            {"title": f"delegate-{name}", "status": "live", "source": "agent",
             "autonomy": "delegate"},
            f"# Delegate: {name}\n\nbrief:\n{brief}\n",
        )
        # sandbox confinement is the gate; intent gate optional on top
        lock.atomic_write(path, text, gate=gate, action="delegate")
        return path

    def list_delegates(self) -> list:
        if not os.path.isdir(self.dir):
            return []
        return [f for f in os.listdir(self.dir) if f.endswith(".md")]

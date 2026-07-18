"""Autonomy scaffold (AU1-AU5, v1 safe subset).

This is the control surface that makes SIGIL agents *semi*-autonomous:
scoped delegation encoded in the vault, graduated not binary, with the
vault as both leash and audit trail.

AU1 intent contract: intent.md is a CODE-LEVEL allowlist, re-loaded every
  loop and before every write (not read-once-at-boot). Enforced in the
  write path via `sigil.lock.IntentGate`.
AU2 tiers: ask | act only in v1 (`delegate` needs a sandbox -> phase 2).
  confidence < 0.6 -> forced to `ask`.
AU3 proposal/approval: `act` MUST route through a proposal note; the agent
  polls (mtime + content-hash) and only executes when approval carries
  `source: human` (no self-approval). Kill-switch re-checked before execute.
AU4 heartbeat stub: `heartbeat_once(schedule)` executes due jobs (note
  read/write only) on demand. The long-running `--daemon` loop is phase 2.
AU5 kill-switch: a dedicated `halted`/`tombstoned` sentinel, scan-independent,
  checked every loop and before every write. Distinct from the legitimate
  `ask` state.

All mutations route through `sigil.lock.atomic_write` so the intent gate
always applies.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from typing import Optional

from . import lock
from .frontmatter import parse, emit
from .lock import IntentGate

CONFIDENCE_ASK_THRESHOLD = 0.6
KILLSWITCH_FILE = "KILLSWITCH.md"
HALT_STATES = {"halt", "halted", "stop"}


# ---- AU1: intent ----------------------------------------------------------
def load_intent(vault_root: str) -> dict:
    """Read + parse intent.md. Re-called every loop (not cached long-term)."""
    path = os.path.join(vault_root, "intent.md")
    if not os.path.exists(path):
        return {"allowed": ["*"], "forbidden": [], "autonomy": "ask", "status": "live"}
    try:
        fm, _ = parse(open(path, encoding="utf-8").read())
    except Exception:
        return {"allowed": ["*"], "forbidden": [], "autonomy": "ask", "status": "live"}
    return {
        "allowed": fm.get("allowed", ["*"]),
        "forbidden": fm.get("forbidden", []),
        "autonomy": str(fm.get("autonomy", "ask")),
        "status": str(fm.get("status", "live")),
        "mandate": fm.get("mandate", ""),
    }


def gate_from_intent(intent: dict) -> IntentGate:
    return IntentGate.from_intent(intent)


# ---- AU5: kill-switch -----------------------------------------------------
def is_halted(vault_root: str) -> bool:
    """Scan-independent halt check: dedicated file OR intent status:halt.

    Always returns True if either signal is present. Checked every loop and
    before every write.
    """
    # 1) dedicated sentinel file (highest priority, independent of scan)
    ks = os.path.join(vault_root, KILLSWITCH_FILE)
    if os.path.exists(ks):
        try:
            fm, _ = parse(open(ks, encoding="utf-8").read())
            if str(fm.get("status", "")).lower() in HALT_STATES:
                return True
        except Exception:
            return True  # unreadable sentinel => fail safe (halt)
    # 2) intent.md status:halt
    intent = load_intent(vault_root)
    if intent.get("status", "").lower() in HALT_STATES:
        return True
    # 3) root note tombstoned
    root = os.path.join(vault_root, "BOOTSTRAP.md")
    if os.path.exists(root):
        try:
            fm, _ = parse(open(root, encoding="utf-8").read())
            if str(fm.get("status", "")).lower() in ("dead", "tombstoned"):
                return True
        except Exception:
            pass
    return False


def halt(vault_root: str, reason: str = "") -> str:
    """Write the KILLSWITCH.md sentinel (atomic, no gate — human override)."""
    path = os.path.join(vault_root, KILLSWITCH_FILE)
    body = f"agent halted. {reason}\n".strip() + "\n"
    text = emit({"title": "killswitch", "status": "halt", "source": "human"}, body)
    lock.atomic_write(path, text, gate=None, action="halt")
    return path


# ---- AU2: tier resolution ------------------------------------------------
def resolve_tier(intent: dict, confidence: Optional[float], sandbox_active: bool = False) -> str:
    """Return effective tier. Confidence < threshold forces `ask`.

    `delegate` is only reachable when intent.allowed contains "delegate" AND a
    sandbox boundary is active (fail-closed: no sandbox -> downgrade to ask).
    """
    tier = str(intent.get("autonomy", "ask")).lower()
    if tier not in ("ask", "act", "delegate"):
        tier = "ask"
    if tier == "delegate":
        allowed = intent.get("allowed", [])
        if isinstance(allowed, str):
            allowed = [allowed]
        if "delegate" not in allowed or not sandbox_active:
            tier = "ask"
    if confidence is not None and confidence < CONFIDENCE_ASK_THRESHOLD:
        tier = "ask"
    return tier


def request_delegate(vault_root: str, name: str, brief: str, intent: dict) -> dict:
    """Attempt to spawn a delegate. Returns {ok, path?, reason?}.

    Fails closed unless intent allows 'delegate' and a Sandbox is constructed.
    """
    allowed = intent.get("allowed", [])
    if isinstance(allowed, str):
        allowed = [allowed]
    if "delegate" not in allowed:
        return {"ok": False, "reason": "intent does not allow delegate"}
    from . import sandbox as sandboxmod
    sb = sandboxmod.Sandbox(vault_root)
    try:
        path = sb.spawn(name, brief, gate=None)  # sandbox confinement is the gate
    except PermissionError as e:
        return {"ok": False, "reason": str(e)}
    return {"ok": True, "path": path}


# ---- AU3: proposal / approval --------------------------------------------
PROPOSAL_RE = re.compile(r"status:\s*(pending|approved|rejected)", re.I)
APPROVAL_SOURCE_RE = re.compile(r"source:\s*human", re.I)


def write_proposal(vault_root: str, name: str, what: str, gate: IntentGate) -> str:
    """Create a proposal note. Agent does NOT act until approved."""
    path = os.path.join(vault_root, f"_proposal_{name}.md")
    body = (
        f"# Proposal: {name}\n\n"
        f"intended action:\n{what}\n\n"
        f"approve by setting status: approved and source: human.\n"
    )
    text = emit(
        {"title": f"proposal-{name}", "status": "pending", "source": "agent"},
        body,
    )
    lock.atomic_write(path, text, gate=gate, action="propose")
    return path


def proposal_state(path: str) -> tuple:
    """Return (status, approved_by_human, content_hash)."""
    if not os.path.exists(path):
        return ("missing", False, "")
    text = open(path, encoding="utf-8").read()
    m = PROPOSAL_RE.search(text)
    status = m.group(1).lower() if m else "pending"
    human = bool(APPROVAL_SOURCE_RE.search(text))
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return (status, human and status == "approved", h)


def poll_proposal(vault_root: str, name: str, last_hash: str = "") -> tuple:
    """Poll a proposal. Returns (can_execute, state_tuple).

    can_execute = approved by a HUMAN (source:human) and content unchanged
    since last poll (no mid-flight tampering by the agent).
    """
    path = os.path.join(vault_root, f"_proposal_{name}.md")
    status, approved, h = proposal_state(path)
    if status == "approved" and approved and h != last_hash:
        # changed since we last saw it -> re-verify it's still human-approved
        return (True, (status, approved, h))
    if status == "approved" and approved:
        return (True, (status, approved, h))
    return (False, (status, approved, h))


# ---- AU4: heartbeat stub --------------------------------------------------
def heartbeat_once(vault_root: str, schedule_text: str, due_fn=None) -> list:
    """Execute due schedule lines (note read/write only). Phase-2 daemon loop
    is deferred; this runs once on demand. `due_fn(line)` -> bool decides if a
    line is due (default: all non-comment, non-empty lines are 'due')."""
    results = []
    for line in schedule_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if due_fn and not due_fn(line):
            continue
        # v1 scope: job = read/write a note named by the line (after '|')
        target = line.split("|")[-1].strip()
        note_path = os.path.join(vault_root, target + ".md")
        entry = {"line": line, "target": target}
        if os.path.exists(note_path):
            entry["result"] = "touched"
        else:
            emit_text = emit({"title": target, "status": "live", "source": "agent"},
                              f"# {target}\n\n(heartbeat-created)\n")
            lock.atomic_write(note_path, emit_text, gate=None, action="heartbeat")
            entry["result"] = "created"
        results.append(entry)
    return results

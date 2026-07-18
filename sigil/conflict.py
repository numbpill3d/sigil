"""Conflict protocol (F3).

When the agent wants to assert a belief that collides with an existing
`claim:` in a human/agent note, it must NOT silently overwrite. SIGIL
resolves conflicts by provenance tier:

  human  > agent  > ingested

Resolution:
  - If the conflicting claim's source tier is >= the new claim's tier:
    DEFAULT TO HUMAN. The agent records the disagreement in a new
    `conflict-log` child note and proceeds with the human value (or asks).
  - If the new claim's tier is higher (agent vs ingested), the agent may
    update, but records the supersession in the conflict-log.
  - Claims are surfaced via the `claim:` key in frontmatter (a short
    assertion string) or inline `claim(...)`. We support the frontmatter
    `claim` field (string or list).

The conflict log keeps `_conflict_log.md` in the vault root with one entry
per detected conflict: {timestamp, note, existing, proposed, resolution}.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from . import lock
from .frontmatter import parse, emit

TIER = {"human": 3, "agent": 2, "ingested": 1}


@dataclass
class Conflict:
    note: str
    claim_field: str
    existing: str
    existing_source: str
    proposed: str
    proposed_source: str
    resolution: str  # "kept_human" | "agent_over_ingested" | "escalated"
    timestamp: int


def _claim_and_source(note_path: str):
    try:
        fm, _ = parse(open(note_path, encoding="utf-8").read())
    except Exception:
        return None, "ingested"
    claim = fm.get("claim")
    if isinstance(claim, list):
        claim = " | ".join(str(c) for c in claim)
    src = str(fm.get("source", "ingested"))
    return claim, src


def detect_conflict(
    vault_root: str,
    note_stem: str,
    proposed_claim: str,
    proposed_source: str = "agent",
) -> Optional[Conflict]:
    """Compare a proposed claim against the existing note's `claim`.

    Returns a Conflict if the note has a `claim` and it differs; resolution
    is decided by tier. Does NOT write — caller chooses to apply or surface.
    """
    note_path = os.path.join(vault_root, note_stem + ".md")
    if not os.path.exists(note_path):
        return None
    existing, existing_src = _claim_and_source(note_path)
    if existing is None or existing == proposed_claim:
        return None
    e_tier = TIER.get(existing_src, 1)
    p_tier = TIER.get(proposed_source, 2)
    if e_tier >= p_tier:
        resolution = "kept_human" if existing_src == "human" else "escalated"
    else:
        resolution = "agent_over_ingested"
    return Conflict(
        note=note_stem, claim_field="claim", existing=existing,
        existing_source=existing_src, proposed=proposed_claim,
        proposed_source=proposed_source, resolution=resolution,
        timestamp=int(time.time()),
    )


def record_conflict(vault_root: str, conflict: Conflict, gate=None) -> str:
    """Append the conflict to the vault's `_conflict_log.md` (atomic)."""
    log_path = os.path.join(vault_root, "_conflict_log.md")
    entry = (
        f"- [{conflict.timestamp}] {conflict.note}: "
        f"existing({conflict.existing_source})={conflict.existing!r} "
        f"vs proposed({conflict.proposed_source})={conflict.proposed!r} "
        f"=> {conflict.resolution}\n"
    )
    if os.path.exists(log_path):
        body = open(log_path, encoding="utf-8").read()
        if "---" in body:
            _, b = parse(body)
            body = b
    else:
        body = ""
    body = body + entry
    text = emit({"title": "conflict-log", "status": "live", "source": "agent"}, body)
    lock.atomic_write(log_path, text, gate=gate, action="conflict")
    return log_path

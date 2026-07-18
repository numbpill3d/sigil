"""Persona synthesis (F4).

The agent's "voice" is derived from a `persona.md` note (hatched by default),
NOT hard-coded. We extract `voice`, `tone`, and `rules` and render a system
prompt. If persona.md is missing, we fall back to a sane default and record
it. The schema is pinned (see plan Task 9 fixtures): `voice`, `tone`,
`rules` (list). Extra keys are ignored.

`synthesize(vault_root)` returns the system-prompt string. `drift_detect`
compares two persona dicts and reports changed fields (phase-2 hook; we
implement the compare only).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from .frontmatter import parse, emit
from . import lock

DEFAULT_PERSONA = {
    "voice": "direct, lowercase, no fluff",
    "tone": "analytical",
    "rules": ["never invent data", "respect human notes as authoritative"],
}


@dataclass
class Persona:
    voice: str
    tone: str
    rules: list = field(default_factory=list)
    source: str = "default"

    def system_prompt(self) -> str:
        rules = "\n".join(f"- {r}" for r in self.rules)
        return (
            f"# Persona\n"
            f"voice: {self.voice}\n"
            f"tone: {self.tone}\n"
            f"rules:\n{rules}\n"
        )


def load_persona(vault_root: str) -> Persona:
    path = os.path.join(vault_root, "persona.md")
    if not os.path.exists(path):
        return Persona(**DEFAULT_PERSONA, source="default")
    try:
        fm, _ = parse(open(path, encoding="utf-8").read())
    except Exception:
        return Persona(**DEFAULT_PERSONA, source="default")
    voice = str(fm.get("voice", DEFAULT_PERSONA["voice"]))
    tone = str(fm.get("tone", DEFAULT_PERSONA["tone"]))
    rules = fm.get("rules", DEFAULT_PERSONA["rules"])
    if not isinstance(rules, list):
        rules = [str(rules)]
    return Persona(voice=voice, tone=tone, rules=[str(r) for r in rules], source="persona.md")


def persona_hash(vault_root: str) -> str:
    """Stable hash of the current persona.md frontmatter (phase-2 drift)."""
    import hashlib
    path = os.path.join(vault_root, "persona.md")
    if not os.path.exists(path):
        return "default"
    try:
        fm, _ = parse(open(path, encoding="utf-8").read())
    except Exception:
        return "default"
    norm = {k: fm.get(k) for k in ("voice", "tone", "rules")}
    return hashlib.sha256(repr(norm).encode("utf-8")).hexdigest()[:16]


def check_drift(vault_root: str, gate=None) -> dict:
    """Compare current persona to last-seen snapshot. If changed (and not
    first run), write a `_persona_drift.md` note and update the stored
    snapshot.

    Returns {"changed": bool, "fields": [...], "hash": str}. First run just
    records the baseline (changed=False). Uses `lock.atomic_write` so the
    intent gate applies to the drift note.
    """
    import json
    cur = load_persona(vault_root)
    cur_dict = {"voice": cur.voice, "tone": cur.tone, "rules": cur.rules}
    new_hash = persona_hash(vault_root)
    store = os.path.join(vault_root, ".sigil", "persona.snapshot.json")
    if not os.path.exists(store):
        os.makedirs(os.path.dirname(store), exist_ok=True)
        json.dump({"hash": new_hash, "persona": cur_dict}, open(store, "w", encoding="utf-8"))
        return {"changed": False, "fields": [], "hash": new_hash}
    prev = json.load(open(store, encoding="utf-8"))
    if prev.get("hash") == new_hash:
        return {"changed": False, "fields": [], "hash": new_hash}
    fields = drift_detect(prev.get("persona", {}), cur_dict)
    body = (
        f"# Persona drift detected\n\n"
        f"changed fields: {', '.join(fields) or '(structural)'}\n"
        f"new voice: {cur.voice}\nnew tone: {cur.tone}\n"
        f"new rules: {cur.rules}\n\n"
        f"review and confirm, or revert persona.md.\n"
    )
    text = emit({"title": "persona-drift", "status": "live", "source": "agent"}, body)
    lock.atomic_write(os.path.join(vault_root, "_persona_drift.md"), text, gate=gate, action="drift")
    json.dump({"hash": new_hash, "persona": cur_dict}, open(store, "w", encoding="utf-8"))
    return {"changed": True, "fields": fields, "hash": new_hash}


def drift_detect(old: dict, new: dict) -> list:
    """Return list of persona keys whose value changed."""
    changed = []
    for k in set(old) | set(new):
        if old.get(k) != new.get(k):
            changed.append(k)
    return changed

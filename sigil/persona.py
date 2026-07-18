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

from .frontmatter import parse

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


def drift_detect(old: dict, new: dict) -> list:
    """Return list of changed persona keys (phase-2 hook)."""
    changed = []
    for k in set(old) | set(new):
        if old.get(k) != new.get(k):
            changed.append(k)
    return changed

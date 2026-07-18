"""Provenance: every agent write is stamped.

F5. The vault is untrusted-data-safe AND auditable: every note the agent
writes carries a `provenance` frontmatter block recording `source`
(agent/human/ingested), `derived_from` (which notes it was assembled from,
as a list of stems), `model` (which provider/model produced it), and
`confidence` (0..1, optional). Human notes are never overwritten; agent
writes go through `lock.atomic_write` so the intent gate still applies.

This module is the single coerced path for agent-authored provenance — callers
pass their assembled context stems + model id and get back a stamped note
body. The stamp is appended to frontmatter; the body is preserved (or set).
"""

from __future__ import annotations

import os
import time
from typing import Optional, Sequence

from . import lock
from .frontmatter import parse, emit
from .lock import IntentGate


def stamp(
    path: str,
    body: str,
    *,
    source: str = "agent",
    derived_from: Optional[Sequence[str]] = None,
    model: str = "null",
    confidence: Optional[float] = None,
    gate: Optional[IntentGate] = None,
    preserve_body: bool = True,
) -> str:
    """Write `body` to `path` with a provenance stamp. Returns the written text.

    If the file exists and `preserve_body`, the existing body is kept and only
    frontmatter is merged (provenance + timestamps). `derived_from` / `model`
    / `confidence` are recorded under `provenance:`.
    """
    fm: dict = {}
    existing_body = body
    if preserve_body and os.path.exists(path):
        try:
            fm, existing_body = parse(open(path, encoding="utf-8").read())
        except Exception:
            fm, existing_body = {}, existing_body

    prov = {
        "source": source,
        "derived_from": list(derived_from or []),
        "model": model,
        "written_at": int(time.time()),
    }
    if confidence is not None:
        prov["confidence"] = round(float(confidence), 4)
    fm.setdefault("title", os.path.splitext(os.path.basename(path))[0])
    fm["source"] = source if source != "agent" else fm.get("source", "agent")
    fm["provenance"] = {**fm.get("provenance", {}), **prov}
    fm.setdefault("created", int(time.time()))
    text = emit(fm, existing_body)
    lock.atomic_write(path, text, gate=gate, action="stamp")
    return text

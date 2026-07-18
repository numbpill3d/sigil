"""Frontmatter parse/emit backed by PyYAML.

SIGIL notes are markdown files with a leading YAML block delimited by
`---` fences. We deliberately use PyYAML (not a hand-rolled parser) for
both read and write: a broken emitter can corrupt a user's vault, and
human-authored frontmatter is far too varied for a toy parser.

Convention: only the 11 promoted Note fields are first-class; every
feature-specific key (confidence, derived_from, claim, task, role,
decay, intent fields, ...) lives in `frontmatter` and is read from
there. This module never drops unknown keys.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

_FENCE = re.compile(r"^---\s*$", re.MULTILINE)


class FrontmatterError(ValueError):
    """Raised when frontmatter is malformed or missing its closing fence."""


def split(text: str) -> tuple[dict[str, Any], str]:
    """Split raw note text into (frontmatter_dict, body).

    Raises FrontmatterError if a leading fence has no closing fence, or if
    the YAML fails to parse. A note with no frontmatter returns ({}, text).
    """
    stripped = text.lstrip("\ufeff")  # strip BOM
    if not stripped.startswith("---"):
        return {}, text
    # Scan for the closing fence, keeping the original string so the body's
    # trailing newlines are preserved exactly (splitlines() would drop them).
    nl = "\n"
    first_nl = stripped.find(nl)
    if first_nl == -1:
        raise FrontmatterError("unterminated frontmatter block")
    body_start = None
    search_from = first_nl + 1
    while True:
        next_nl = stripped.find(nl, search_from)
        line_end = next_nl if next_nl != -1 else len(stripped)
        line = stripped[search_from:line_end].strip()
        if line in ("---", "..."):
            body_start = (next_nl + 1) if next_nl != -1 else len(stripped)
            break
        if next_nl == -1:
            raise FrontmatterError("unterminated frontmatter block")
        search_from = next_nl + 1
    fm_text = stripped[first_nl + 1 : body_start].rstrip("\n")
    # strip the closing fence line if it ended up inside fm_text
    if fm_text.endswith("---") or fm_text.endswith("..."):
        fm_text = fm_text[: fm_text.rfind("\n")].rstrip("\n")
    body = stripped[body_start:]
    try:
        data = yaml.safe_load(fm_text) if fm_text.strip() else {}
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"invalid YAML frontmatter: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise FrontmatterError("frontmatter must be a mapping")
    return data, body


def parse(text: str) -> tuple[dict[str, Any], str]:
    """Alias for split(); returns (frontmatter, body)."""
    return split(text)


def emit(frontmatter: dict[str, Any], body: str) -> str:
    """Serialize (frontmatter, body) back into a note string.

    Key order is preserved (PyYAML sorts keys by default; we use
    sort_keys=False). Unknown keys are kept verbatim. Body is never
    mutated; a missing trailing newline is not invented.
    """
    if not frontmatter:
        return body
    fm_text = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    return f"---\n{fm_text}---\n{body}"


def roundtrip(text: str) -> tuple[dict[str, Any], str]:
    """Parse then re-emit then re-parse; returns the second parse + body.

    Useful for asserting emit does not corrupt data.
    """
    fm, body = split(text)
    out = emit(fm, body)
    return split(out)

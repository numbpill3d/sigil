"""Hatch: GERMINATE (fresh vault) or INCUBATE (adopt existing tree).

GERMINATE writes the greenfield template into an empty target.
INCUBATE adopts an existing markdown tree (with or without `.obsidian`),
copying notes into the vault root while applying an EXCLUDE filter so
secret/irrelevant files are never ingested.

Both modes route through `sigil.lock.atomic_write` (so the intent gate
applies to agent-authored files) and NEVER write outside `target`. Hatching
`~` or any ancestor/path above an explicit target is refused — the agent
must name a directory, not a home.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Iterable

from . import lock

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates", "greenfield_vault")

# name-based excludes (substring match, case-insensitive)
NAME_EXCLUDES = [".obsidian", "node_modules", ".git", ".trash", "templates"]
SECRET_NAME_HINTS = ["secret", ".env", ".key", "credential", "id_rsa", "id_ed25519", "token"]

# content-based secret heuristics (case-insensitive)
SECRET_PATTERNS = [
    re.compile(r"sk-[a-z0-9]{20,}"),            # openai/long api keys
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),            # aws access key id
    re.compile(r"ghp_[a-z0-9]{20,}"),           # github pat
    re.compile(r"xox[baprs]-[0-9a-z-]{10,}"),   # slack tokens
]


class HatchError(ValueError):
    """Raised for invalid hatch targets (e.g. `~`)."""


def _is_excluded(name: str) -> bool:
    low = name.lower()
    if any(part in low for part in NAME_EXCLUDES):
        return True
    if name.startswith(".") and name not in (".gitignore",):
        return True
    if any(h in low for h in SECRET_NAME_HINTS):
        return True
    return False


def _looks_secret(text: str) -> bool:
    low = text.lower()
    if any(h in low for h in SECRET_NAME_HINTS):
        return True
    return any(p.search(text) for p in SECRET_PATTERNS)


def _refuse_home(target: str) -> None:
    real = os.path.realpath(target)
    home = os.path.realpath(os.path.expanduser("~"))
    if real == home or real == "/" or real.startswith(home + os.sep):
        raise HatchError(f"refusing to hatch home/root path: {target}")


def germinate(target: str) -> str:
    """Create a fresh vault from the template. Returns the target path."""
    _refuse_home(target)
    real = os.path.realpath(target)
    os.makedirs(real, exist_ok=True)
    tmpl = os.path.realpath(TEMPLATE_DIR)
    for fn in os.listdir(tmpl):
        src = os.path.join(tmpl, fn)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(real, fn)
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
        lock.atomic_write(dst, text, gate=None, action="hatch")
    # mark as an obsidian vault for nice UX (optional, non-destructive)
    os.makedirs(os.path.join(real, ".obsidian"), exist_ok=True)
    return real


def incubate(target: str, include_outside: bool = False) -> dict:
    """Adopt an existing markdown tree. Returns a report dict.

    `include_outside` is reserved; in v1 all sources must live under target.
    Excluded secret/irrelevant files are reported, never copied.
    """
    _refuse_home(target)
    real = os.path.realpath(target)
    if not os.path.isdir(real):
        raise HatchError(f"incubate target is not a directory: {target}")
    copied, excluded = [], []
    for dirpath, dirnames, filenames in os.walk(real):
        # never descend into our own index / template dirs
        dirnames[:] = [d for d in dirnames if d not in (".sigil", ".obsidian", "node_modules")]
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, real)
            if _is_excluded(fn) or _is_excluded(rel):
                excluded.append(rel)
                continue
            text = Path(full).read_text(encoding="utf-8", errors="replace")
            if _looks_secret(text):
                excluded.append(rel + " (secret-content)")
                continue
            dst = os.path.join(real, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            lock.atomic_write(dst, text, gate=None, action="incubate")
            copied.append(rel)
    # ensure intent.md + persona exist for the adopted vault (non-destructive)
    _ensure_intent(real)
    return {"copied": copied, "excluded": excluded, "root": real}


def _ensure_intent(real: str) -> None:
    tmpl = os.path.realpath(TEMPLATE_DIR)
    for fn in ("intent.md", "persona.md", "BOOTSTRAP.md", "MOC.md", "schedule.md"):
        dst = os.path.join(real, fn)
        if not os.path.exists(dst):
            src = os.path.join(tmpl, fn)
            if os.path.exists(src):
                with open(src, encoding="utf-8") as fh:
                    lock.atomic_write(dst, fh.read(), gate=None, action="hatch")


def hatch(target: str, mode: str, include_outside: bool = False) -> dict:
    mode = mode.lower()
    if mode in ("germinate", "fresh"):
        root = germinate(target)
        return {"mode": "germinate", "root": root}
    if mode in ("incubate", "adopt"):
        return incubate(target, include_outside=include_outside)
    raise HatchError(f"unknown hatch mode: {mode}")

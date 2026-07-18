"""Vault: scan markdown notes into a link graph with incremental indexing.

The vault is the agent's memory substrate. A `Vault` walks a directory of
`*.md` files, parses frontmatter (via `sigil.frontmatter`), extracts
`[[wikilinks]]`, and builds a `LinkGraph` (forward links + backlinks).
The graph is persisted to `.sigil/graph.json` so re-scans are incremental
(mtime-diff) instead of re-parsing every file every session — the real
scaling ceiling is full re-parse, not link traversal.

All `[[link]]` resolution is confined to the vault root: `..` and symlink
escapes raise `PathEscapeError`. This is a security boundary, not a
convenience — see Task 12.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .frontmatter import parse, FrontmatterError

LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
GRAPH_FILE = ".sigil/graph.json"

# Promoted Note fields per plan (Task 2). All other keys live in frontmatter.
DEFAULT_HALF_LIFE = 90  # days


class PathEscapeError(ValueError):
    """Raised when a [[link]] resolves outside the vault root."""


@dataclass
class Note:
    path: str
    title: str
    body: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    links: list[str] = field(default_factory=list)
    backlinks: list[str] = field(default_factory=list)
    created: float = 0.0
    half_life: float = DEFAULT_HALF_LIFE
    source: str = "agent"
    status: str = "live"
    autonomy: str = ""

    @property
    def stem(self) -> str:
        return Path(self.path).stem


@dataclass
class LinkGraph:
    notes: dict[str, Note] = field(default_factory=dict)
    edges: dict[str, list[str]] = field(default_factory=dict)  # stem -> [stem]
    backedges: dict[str, list[str]] = field(default_factory=dict)
    mtimes: dict[str, float] = field(default_factory=dict)
    revision: int = 0

    def add(self, note: Note) -> None:
        self.notes[note.stem] = note
        self.edges[note.stem] = list(note.links)
        for target in note.links:
            self.backedges.setdefault(target, [])
            if note.stem not in self.backedges[target]:
                self.backedges[target].append(note.stem)

    def drop(self, stem: str) -> None:
        self.notes.pop(stem, None)
        self.edges.pop(stem, None)
        self.backedges.pop(stem, None)
        for src, targets in self.backedges.items():
            if stem in targets:
                targets.remove(stem)


class Vault:
    def __init__(self, root: str):
        self.root = os.path.realpath(root)
        self.graph = LinkGraph()
        self.index_path = os.path.join(self.root, GRAPH_FILE)

    # ---- path confinement -------------------------------------------------
    def resolve_link(self, link: str) -> str:
        """Resolve a [[link]] to an absolute path, confined to root."""
        # links may be "note" or "note#heading" or "path/note"
        target = link.split("#", 1)[0].strip()
        candidate = os.path.realpath(os.path.join(self.root, target + ".md"))
        if candidate != self.root and not candidate.startswith(self.root + os.sep):
            raise PathEscapeError(f"link '{link}' escapes vault root")
        return candidate

    # ---- parsing ----------------------------------------------------------
    def _parse_note(self, path: str) -> Note:
        text = Path(path).read_text(encoding="utf-8")
        try:
            fm, body = parse(text)
        except FrontmatterError:
            fm, body = {}, text
        links = []
        for m in LINK_RE.finditer(body):
            target = m.group(1).split("#", 1)[0].strip()
            if target:
                links.append(target)
        stem = Path(path).stem
        created = float(fm.get("created", os.path.getctime(path)))
        return Note(
            path=path,
            title=str(fm.get("title", stem)),
            body=body,
            frontmatter=fm,
            links=links,
            created=created,
            half_life=float(fm.get("half_life", DEFAULT_HALF_LIFE)),
            source=str(fm.get("source", "agent")),
            status=str(fm.get("status", "live")),
            autonomy=str(fm.get("autonomy", "")),
        )

    # ---- scanning ---------------------------------------------------------
    def scan(self, force: bool = False) -> LinkGraph:
        """Scan the vault. Incremental unless `force`: only re-parse files
        whose mtime changed since the last index; otherwise reuse graph.json."""
        if not force:
            self._load_index()
        md_files = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            # skip the index dir
            dirnames[:] = [d for d in dirnames if not d.startswith(".sigil")]
            for fn in filenames:
                if fn.endswith(".md"):
                    md_files.append(os.path.join(dirpath, fn))
        current_mtimes = {f: os.path.getmtime(f) for f in md_files}
        if not force and self.graph.mtimes:
            # reuse: build set of changed/added/removed
            changed = [
                f for f in md_files
                if self.graph.mtimes.get(f) != current_mtimes[f]
            ]
            # files never seen before (new) are also "changed" -> add them
            new_files = [f for f in md_files if f not in self.graph.mtimes]
            changed.extend(new_files)
            removed = [f for f in self.graph.mtimes if f not in current_mtimes]
            for f in removed:
                self.graph.drop(Path(f).stem)
            for f in changed:
                note = self._parse_note(f)
                if note.stem in self.graph.notes:
                    self.graph.drop(note.stem)
                self.graph.add(note)
                self.graph.mtimes[f] = current_mtimes[f]
            # unchanged files: keep existing Note objects in graph
            self.graph.revision += 1
            self._check_drift()
            return self.graph
        # full scan
        self.graph = LinkGraph()
        for f in md_files:
            note = self._parse_note(f)
            self.graph.add(note)
            self.graph.mtimes[f] = current_mtimes[f]
        self.graph.revision += 1
        self._save_index()
        self._check_drift()
        return self.graph

    # ---- drift ------------------------------------------------------------
    def _check_drift(self) -> dict:
        """Run persona drift detection on every scan (phase-2 P2-5).

        Safe to call always: if persona.md is absent it falls back to default
        and records a baseline. Returns the drift result dict.
        """
        from . import persona as personamod
        try:
            return personamod.check_drift(self.root)
        except Exception:
            return {"changed": False, "fields": [], "hash": "error", "error": True}

    # ---- persistence ------------------------------------------------------
    def _load_index(self) -> bool:
        if not os.path.exists(self.index_path):
            return False
        try:
            with open(self.index_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return False
        self.graph.revision = data.get("revision", 0)
        self.graph.mtimes = data.get("mtimes", {})
        # notes/edges are rebuilt by incremental scan from mtimes; but if the
        # index also stores note stubs we restore them. We store light stubs.
        for stem, stub in data.get("notes", {}).items():
            self.graph.notes[stem] = Note(
                path=stub["path"], title=stub.get("title", stem),
                body="", frontmatter=stub.get("frontmatter", {}),
                links=stub.get("links", []), created=stub.get("created", 0.0),
                half_life=stub.get("half_life", DEFAULT_HALF_LIFE),
                source=stub.get("source", "agent"),
                status=stub.get("status", "live"),
                autonomy=stub.get("autonomy", ""),
            )
        self.graph.edges = data.get("edges", {})
        self.graph.backedges = data.get("backedges", {})
        return True

    def _save_index(self) -> None:
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        notes_stub = {
            stem: {
                "path": n.path, "title": n.title,
                "frontmatter": n.frontmatter, "links": n.links,
                "created": n.created, "half_life": n.half_life,
                "source": n.source, "status": n.status, "autonomy": n.autonomy,
            }
            for stem, n in self.graph.notes.items()
        }
        data = {
            "revision": self.graph.revision,
            "mtimes": self.graph.mtimes,
            "notes": notes_stub,
            "edges": self.graph.edges,
            "backedges": self.graph.backedges,
        }
        with open(self.index_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

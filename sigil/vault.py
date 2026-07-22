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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .frontmatter import parse, FrontmatterError

LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
GRAPH_FILE = ".sigil/graph.json"
DEFAULT_HALF_LIFE = 90  # days


class PathEscapeError(ValueError):
    """Raised when a [[link]] resolves outside the vault root."""


@dataclass
class Note:
    key: str
    path: str
    title: str
    body: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    links: list[str] = field(default_factory=list)  # raw wikilink targets
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
    notes: dict[str, Note] = field(default_factory=dict)  # key -> Note
    edges: dict[str, list[str]] = field(default_factory=dict)  # key -> [key]
    backedges: dict[str, list[str]] = field(default_factory=dict)  # key -> [key]
    mtimes: dict[str, float] = field(default_factory=dict)
    revision: int = 0
    remote_of: dict[str, str] = field(default_factory=dict)  # key -> remote name
    stem_index: dict[str, list[str]] = field(default_factory=dict)  # stem -> [key]

    def add(self, note: Note) -> None:
        old = self.notes.get(note.key)
        if old is not None:
            self._deindex(old)
        self.notes[note.key] = note
        self._index(note)

    def _index(self, note: Note) -> None:
        keys = self.stem_index.setdefault(note.stem, [])
        if note.key not in keys:
            keys.append(note.key)
            keys.sort()

    def _deindex(self, note: Note) -> None:
        keys = self.stem_index.get(note.stem, [])
        if note.key in keys:
            keys.remove(note.key)
        if not keys and note.stem in self.stem_index:
            self.stem_index.pop(note.stem, None)

    def drop(self, key: str) -> None:
        note = self.notes.pop(key, None)
        if note is not None:
            self._deindex(note)
        self.edges.pop(key, None)
        self.backedges.pop(key, None)
        self.remote_of.pop(key, None)
        for targets in self.edges.values():
            while key in targets:
                targets.remove(key)
        for targets in self.backedges.values():
            while key in targets:
                targets.remove(key)

    def rebuild_edges(self, resolver: Callable[[str, Optional[str]], Optional[str]]) -> None:
        self.edges = {}
        self.backedges = {}
        for key, note in self.notes.items():
            resolved: list[str] = []
            seen: set[str] = set()
            for target in note.links:
                tgt_key = resolver(target, key)
                if tgt_key and tgt_key not in seen:
                    resolved.append(tgt_key)
                    seen.add(tgt_key)
            self.edges[key] = resolved
            for tgt_key in resolved:
                self.backedges.setdefault(tgt_key, [])
                if key not in self.backedges[tgt_key]:
                    self.backedges[tgt_key].append(key)


class Vault:
    def __init__(self, root: str):
        self.root = os.path.realpath(root)
        self.graph = LinkGraph()
        self.index_path = os.path.join(self.root, GRAPH_FILE)

    def _key_for_path(self, path: str) -> str:
        rel = os.path.relpath(os.path.realpath(path), self.root)
        rel = rel.replace(os.sep, "/")
        if rel.endswith(".md"):
            rel = rel[:-3]
        return rel

    def _normalize_target(self, link: str) -> str:
        target = link.split("#", 1)[0].strip().replace("\\", "/")
        if target.endswith(".md"):
            target = target[:-3]
        if not target:
            return ""
        if os.path.isabs(target):
            raise PathEscapeError(f"link '{link}' escapes vault root")
        target = os.path.normpath(target).replace("\\", "/")
        if target in (".", ""):
            return ""
        if target == ".." or target.startswith("../"):
            raise PathEscapeError(f"link '{link}' escapes vault root")
        return target

    def resolve_note_key(self, link: str, source_key: Optional[str] = None) -> Optional[str]:
        try:
            target = self._normalize_target(link)
        except PathEscapeError:
            return None
        if not target:
            return None
        if target in self.graph.notes:
            return target
        if source_key:
            sibling = os.path.normpath(os.path.join(os.path.dirname(source_key), target)).replace("\\", "/")
            if sibling in self.graph.notes:
                return sibling
        matches = self.graph.stem_index.get(Path(target).name, [])
        if len(matches) == 1:
            return matches[0]
        root_match = Path(target).name
        if root_match in self.graph.notes:
            return root_match
        return None

    # ---- path confinement -------------------------------------------------
    def resolve_link(self, link: str, source_key: Optional[str] = None) -> str:
        """Resolve a [[link]] to an absolute path, confined to root."""
        target = self._normalize_target(link)
        key = self.resolve_note_key(target, source_key=source_key)
        if key and key in self.graph.notes:
            return self.graph.notes[key].path
        rel = target
        if source_key:
            sibling = os.path.normpath(os.path.join(os.path.dirname(source_key), target)).replace("\\", "/")
            if not sibling.startswith("../") and sibling != "..":
                rel = sibling
        candidate = os.path.realpath(os.path.join(self.root, rel + ".md"))
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
            key=self._key_for_path(path),
            path=os.path.realpath(path),
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
        """Scan the vault. Incremental unless `force`."""
        if not force:
            self._load_index()
        md_files = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".sigil")]
            for fn in filenames:
                if fn.endswith(".md"):
                    md_files.append(os.path.join(dirpath, fn))
        current_mtimes = {f: os.path.getmtime(f) for f in md_files}
        if not force and self.graph.mtimes:
            changed = [f for f in md_files if self.graph.mtimes.get(f) != current_mtimes[f]]
            removed = [f for f in self.graph.mtimes if f not in current_mtimes]
            for f in removed:
                self.graph.drop(self._key_for_path(f))
                self.graph.mtimes.pop(f, None)
            for f in changed:
                note = self._parse_note(f)
                self.graph.add(note)
                self.graph.mtimes[f] = current_mtimes[f]
            self.graph.rebuild_edges(self.resolve_note_key)
            self.graph.revision += 1
            self._save_index()
            self._check_drift()
            return self.graph

        self.graph = LinkGraph()
        for f in md_files:
            note = self._parse_note(f)
            self.graph.add(note)
            self.graph.mtimes[f] = current_mtimes[f]
        self.graph.rebuild_edges(self.resolve_note_key)
        self.graph.revision += 1
        self._save_index()
        self._check_drift()
        return self.graph

    # ---- drift ------------------------------------------------------------
    def _check_drift(self) -> dict:
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
        self.graph = LinkGraph()
        self.graph.revision = data.get("revision", 0)
        self.graph.mtimes = data.get("mtimes", {})
        for saved_key, stub in data.get("notes", {}).items():
            path = os.path.realpath(stub["path"])
            key = stub.get("key") or self._key_for_path(path)
            note = Note(
                key=key,
                path=path,
                title=stub.get("title", Path(path).stem),
                body=stub.get("body", ""),
                frontmatter=stub.get("frontmatter", {}),
                links=stub.get("links", []),
                created=stub.get("created", 0.0),
                half_life=stub.get("half_life", DEFAULT_HALF_LIFE),
                source=stub.get("source", "agent"),
                status=stub.get("status", "live"),
                autonomy=stub.get("autonomy", ""),
            )
            self.graph.add(note)
        self.graph.remote_of = data.get("remote_of", {})
        self.graph.rebuild_edges(self.resolve_note_key)
        return True

    def _save_index(self) -> None:
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        notes_stub = {
            key: {
                "key": n.key,
                "path": n.path,
                "title": n.title,
                "body": n.body,
                "frontmatter": n.frontmatter,
                "links": n.links,
                "created": n.created,
                "half_life": n.half_life,
                "source": n.source,
                "status": n.status,
                "autonomy": n.autonomy,
            }
            for key, n in self.graph.notes.items()
        }
        data = {
            "revision": self.graph.revision,
            "mtimes": self.graph.mtimes,
            "notes": notes_stub,
            "edges": self.graph.edges,
            "backedges": self.graph.backedges,
            "remote_of": self.graph.remote_of,
        }
        with open(self.index_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

"""Vault federation (Phase 2, P2-3).

A note may declare `share: [vault-b]` in frontmatter, meaning its
`[[links]]` may resolve into the named remote vault's graph. This lets one
agent's context walk across vault boundaries — e.g. a personal vault sharing
selected notes into a project vault.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .vault import Vault, LinkGraph, PathEscapeError


class FederatedVault:
    """Primary vault + named remote vaults, linked by `share:`."""

    def __init__(self, primary: Vault, remotes: Optional[Dict[str, Vault]] = None):
        self.primary = primary
        self.remotes: Dict[str, Vault] = dict(remotes or {})
        self.graph: LinkGraph = primary.graph

    def add_remote(self, name: str, vault: Vault) -> None:
        self.remotes[name] = vault

    def scan(self, force: bool = False) -> LinkGraph:
        self.primary.scan(force=force)
        for v in self.remotes.values():
            v.scan(force=force)
        self._merge()
        return self.graph

    def _merge(self) -> None:
        g = self.primary.graph
        remote_of = dict(getattr(g, "remote_of", {}))
        for name, rv in self.remotes.items():
            for key, note in rv.graph.notes.items():
                if key not in g.notes:
                    g.notes[key] = note
                remote_of[key] = name
        g.remote_of = remote_of
        g.rebuild_edges(self.resolve_note_key)
        self.graph = g

    def resolve_note_key(self, link: str, source_key: Optional[str] = None) -> Optional[str]:
        key = self.primary.resolve_note_key(link, source_key=source_key)
        if key:
            return key
        for rv in self.remotes.values():
            key = rv.resolve_note_key(link, source_key=source_key)
            if key:
                return key
        return None

    def resolve_link(self, link: str, source_key: Optional[str] = None) -> str:
        target = link.split("#", 1)[0].strip()
        try:
            p = self.primary.resolve_link(target, source_key=source_key)
            key = self.primary.resolve_note_key(target, source_key=source_key)
            if key in self.primary.graph.notes:
                return p
        except PathEscapeError:
            pass
        for rv in self.remotes.values():
            try:
                p = rv.resolve_link(target, source_key=source_key)
            except PathEscapeError:
                continue
            key = rv.resolve_note_key(target, source_key=source_key)
            if key in rv.graph.notes:
                return p
        raise PathEscapeError(f"link '{link}' not found in primary or any remote")

    def authorized_remotes(self, note_key: str) -> List[str]:
        note = self.primary.graph.notes.get(note_key)
        if not note:
            return []
        shares = note.frontmatter.get("share", [])
        if isinstance(shares, str):
            shares = [shares]
        return [s for s in shares if s in self.remotes]

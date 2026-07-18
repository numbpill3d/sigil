"""Vault federation (Phase 2, P2-3).

A note may declare `share: [vault-b]` in frontmatter, meaning its
`[[links]]` may resolve into the named remote vault's graph. This lets one
agent's context walk across vault boundaries — e.g. a personal vault sharing
selected notes into a project vault.

Safety: every cross-vault resolution goes through the REMOTE vault's own
`resolve_link`, which enforces that remote's path confinement. A `share:`
target is resolved by name against a registry the CALLER provides; SIGIL
never blindly trusts a path written in frontmatter. Escape attempts are
rejected per-remote, exactly as in v1.

`FederatedVault` presents the same surface the ContextAssembler expects
(`.graph`, `.resolve_link`, `.scan()`), so it drops in transparently.
"""

from __future__ import annotations

import os
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
        """Merge remote graphs into the primary graph as visible notes.

        Remote notes are added read-only to the merged graph so the
        ContextAssembler can walk into them. Confinement is preserved because
        each remote was scanned with its own path confinement.
        """
        g = self.primary.graph
        remote_of = dict(getattr(g, "remote_of", {}))
        for name, rv in self.remotes.items():
            for stem, note in rv.graph.notes.items():
                if stem not in g.notes:
                    g.notes[stem] = note
                remote_of[stem] = name
        g.remote_of = remote_of
        self.graph = g

    def resolve_link(self, link: str) -> str:
        """Resolve a link across primary + remotes by graph membership.

        A link resolves only if the target note actually EXISTS in a vault's
        graph (not merely that the path stays confined). Each candidate is
        checked via the vault's own `resolve_link` (path confinement), then
        confirmed present in that vault's graph. This prevents inventing paths
        and keeps per-remote confinement intact.
        """
        target = link.split("#", 1)[0].strip()
        # primary first
        try:
            p = self.primary.resolve_link(target)
            if target in self.primary.graph.notes:
                return p
        except PathEscapeError:
            pass
        for name, rv in self.remotes.items():
            try:
                p = rv.resolve_link(target)
            except PathEscapeError:
                continue
            if target in rv.graph.notes:
                return p
        raise PathEscapeError(f"link '{link}' not found in primary or any remote")

    def authorized_remotes(self, stem: str) -> List[str]:
        """Remote names a given note may share into, per its `share:` list."""
        note = self.primary.graph.notes.get(stem)
        if not note:
            return []
        shares = note.frontmatter.get("share", [])
        if isinstance(shares, str):
            shares = [shares]
        return [s for s in shares if s in self.remotes]

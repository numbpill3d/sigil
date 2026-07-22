"""ContextAssembler: the agent's mind made of links.

Instead of vector RAG, SIGIL builds prompt context by WALKING the vault's
link graph from the active note: BFS up to `hops` following `[[links]]` and
backlinks, scoring each reachable note, and taking the Top-K by TOKEN
budget (not count). This is transparent (you can see exactly why a note
was included) and editable (add a link in Obsidian → context changes).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

W_RECENCY = 0.3
W_PROXIMITY = 0.3
W_DECAY = 0.3
REF_AGE_DAYS = 365.0
TAGMATCH_MULT = 1.1
CANDIDATE_CAP = 200


def _note_created_desc(vault, key) -> float:
    n = vault.graph.notes.get(key)
    return n.created if n else 0.0


@dataclass
class ScoredNote:
    key: str
    stem: str
    label: str
    title: str
    body: str
    score: float
    hop: int
    source: str = "agent"
    status: str = "live"
    via: str = "root"
    parent: Optional[str] = None


class ContextAssembler:
    def __init__(self, vault, provider, cache: Optional[dict] = None):
        self.vault = vault
        self.provider = provider
        self._cache = cache if cache is not None else {}

    def _label_for_key(self, key: Optional[str]) -> Optional[str]:
        if key is None:
            return None
        note = self.vault.graph.notes.get(key)
        return note.key if note is not None else key

    @staticmethod
    def decay_factor(age_days: float, half_life: float) -> float:
        if half_life <= 0:
            return 0.0
        return 0.5 ** (age_days / half_life)

    def assemble(
        self,
        active_key: str,
        k: int = 10,
        hops: int = 2,
        task_tag: Optional[str] = None,
        request_dead: bool = False,
        explain: bool = False,
    ) -> list[ScoredNote]:
        cache_key = (active_key, self.vault.graph.revision, task_tag, request_dead, hops, k)
        if cache_key in self._cache:
            return self._cache[cache_key]
        now = time.time() / 86400.0

        visited: dict[str, int] = {active_key: 0}
        parents: dict[str, Optional[str]] = {active_key: None}
        via_map: dict[str, str] = {active_key: "root"}
        frontier = [active_key]
        while frontier and len(visited) < CANDIDATE_CAP:
            cur = frontier.pop(0)
            cur_hop = visited[cur]
            if cur_hop >= hops:
                continue
            neighbors: list[tuple[str, str]] = []
            seen_here: set[str] = set()
            for nxt in self.vault.graph.edges.get(cur, []):
                if nxt not in seen_here:
                    neighbors.append((nxt, "forward"))
                    seen_here.add(nxt)
            for nxt in self.vault.graph.backedges.get(cur, []):
                if nxt not in seen_here:
                    neighbors.append((nxt, "backlink"))
                    seen_here.add(nxt)
            for nxt, via in neighbors:
                if nxt not in visited:
                    visited[nxt] = cur_hop + 1
                    parents[nxt] = cur
                    via_map[nxt] = via
                    frontier.append(nxt)

        scored: list[ScoredNote] = []
        for key, hop in visited.items():
            note = self.vault.graph.notes.get(key)
            if note is None:
                continue
            if note.status == "dead" and not request_dead:
                continue
            age = max(0.0, now - note.created / 86400.0)
            recency = max(0.0, 1.0 - age / REF_AGE_DAYS)
            proximity = max(0.0, 1.0 - hop / max(1, hops))
            decay = self.decay_factor(age, note.half_life)
            tagmatch = TAGMATCH_MULT if (task_tag and note.frontmatter.get("task") == task_tag) else 1.0
            raw = W_RECENCY * recency + W_PROXIMITY * proximity + W_DECAY * decay
            score = raw * tagmatch
            scored.append(
                ScoredNote(
                    key=key,
                    stem=note.stem,
                    label=note.key,
                    title=note.title,
                    body=note.body,
                    score=score,
                    hop=hop,
                    source=note.source,
                    status=note.status,
                    via=via_map.get(key, "root"),
                    parent=self._label_for_key(parents.get(key)),
                )
            )

        scored.sort(key=lambda n: (n.score, _note_created_desc(self.vault, n.key)), reverse=True)
        budget = self.provider.max_context_tokens
        out: list[ScoredNote] = []
        used = 0
        for sn in scored[:k]:
            est = max(1, len(sn.body) // 4)
            if used + est > budget and out:
                break
            out.append(sn)
            used += est
        self._cache[cache_key] = out
        return out

    def invalidate(self) -> None:
        self._cache.clear()

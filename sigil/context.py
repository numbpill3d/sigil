"""ContextAssembler: the agent's mind made of links.

Instead of vector RAG, SIGIL builds prompt context by WALKING the vault's
link graph from the active note: BFS up to `hops` following `[[links]]` and
backlinks, scoring each reachable note, and taking the Top-K by TOKEN
budget (not count). This is transparent (you can see exactly why a note
was included) and editable (add a link in Obsidian → context changes).

Scoring (pinned weights, see plan Task 6):
  score = recency_w * proximity_w * decay * tagmatch_bonus
  where each factor is normalized to [0,1]:
    recency_w  = 0.3 * (1 - age_days / REF_AGE) clamped to [0,1]
    proximity_w= 0.3 * (1 - hop / max_hops)        clamped to [0,1]
    decay      = 0.5 ** (age_days / half_life)
    tagmatch   = 1.0 if note's `task` tag == task_tag else 1.0 (bonus
                 applied as multiplicative 1.1 on match, base 1.0)
  Final score normalized; tie-break by `created` desc.

Decay (F2): tombstoned notes (`status: dead`) are excluded from
auto-surface; returned only when `request_dead=True`.

Caching (A2): assembled context keyed by (active_note.stem + vault.revision).
Invalidated automatically when the vault revision changes (i.e. on write).

Token cap: `provider.max_context_tokens` bounds total emitted context; we
trim lowest-scored notes until under budget (rough token estimate:
len(chars)/4).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

# scoring weights (must sum conceptually to ~1.0 of the multiplicative mass)
W_RECENCY = 0.3
W_PROXIMITY = 0.3
W_DECAY = 0.3
W_TAGMATCH = 0.1
REF_AGE_DAYS = 365.0  # recency reference window
TAGMATCH_MULT = 1.1
CANDIDATE_CAP = 200


def _note_created_desc(vault, stem) -> float:
    n = vault.graph.notes.get(stem)
    return n.created if n else 0.0


@dataclass
class ScoredNote:
    stem: str
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

    # ---- decay ------------------------------------------------------------
    @staticmethod
    def decay_factor(age_days: float, half_life: float) -> float:
        if half_life <= 0:
            return 0.0
        return 0.5 ** (age_days / half_life)

    # ---- assembly ---------------------------------------------------------
    def assemble(
        self,
        active_stem: str,
        k: int = 10,
        hops: int = 2,
        task_tag: Optional[str] = None,
        request_dead: bool = False,
        explain: bool = False,
    ) -> list[ScoredNote]:
        cache_key = (active_stem, self.vault.graph.revision, task_tag, request_dead, hops, k)
        if cache_key in self._cache:
            return self._cache[cache_key]
        now = time.time() / 86400.0  # days

        # BFS over the link graph (forward + backlinks), candidate-capped
        visited: dict[str, int] = {active_stem: 0}
        parents: dict[str, Optional[str]] = {active_stem: None}
        via_map: dict[str, str] = {active_stem: "root"}
        frontier = [active_stem]
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
        for stem, hop in visited.items():
            note = self.vault.graph.notes.get(stem)
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
                ScoredNote(stem=stem, title=note.title, body=note.body,
                           score=score, hop=hop, source=note.source, status=note.status,
                           via=via_map.get(stem, "root"), parent=parents.get(stem))
            )

        # tie-break: created desc
        scored.sort(key=lambda n: (n.score, _note_created_desc(self.vault, n.stem)), reverse=True)
        # token-budget trim
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

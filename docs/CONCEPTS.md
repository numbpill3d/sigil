# SIGIL — Concepts

## The vault is the agent's mind

A SIGIL agent has no hidden state. Everything it "knows" is a markdown note
you can open, read, and edit in Obsidian. Add a `[[link]]` and the agent's
context changes on the next run. This is the core bet: memory as an editable
graph, not a vector soup.

## Notes and frontmatter

Every note has YAML frontmatter between `---` fences. Promoted fields:

    title, status (live|dead), source (human|agent|ingested),
    half_life (days), created (unix ts), autonomy (ask|act),
    provenance { source, derived_from[], model, written_at, confidence }

Everything else in frontmatter is read on demand (e.g. `claim`, `task`,
`voice`, `tone`, `rules`).

## Link-walk (F1)

Context is built by BFS over the link graph from the active note, following
`[[links]]` and backlinks up to `hops` (default 2). Each reachable note is
scored and the Top-K by token budget are kept. Scoring:

    score = 0.3*recency + 0.3*proximity + 0.3*decay + 0.1*tagmatch

Decay (F2): `0.5 ** (age_days / half_life)`. Tombstoned (`status: dead`)
notes are excluded unless explicitly requested.

## Provenance (F5)

Every agent write is stamped: where it came from, which notes it was derived
from, which model produced it, and a confidence score. You can audit any
belief back to its origin.

## Conflict (F3)

When the agent wants to assert a `claim:` that collides with an existing one,
tier wins: `human > agent > ingested`. Human claims are kept by default; the
disagreement is logged to `_conflict_log.md`.

## Persona (F4)

The agent's voice comes from `persona.md` (`voice`, `tone`, `rules`). No
hard-coded personality.

## Autonomy (AU1-AU5)

- `intent.md` is a CODE-LEVEL allowlist (`allowed`/`forbidden`), re-loaded
  every loop. The write path rejects anything not permitted.
- Tiers: `ask` (confirm) | `act` (execute within allowed). `delegate` is NOT
  in v1 (needs a sandbox). Confidence < 0.6 forces `ask`.
- `act` routes through a proposal note; the agent only executes after a
  HUMAN sets `status: approved` + `source: human`. No self-approval.
- Kill-switch: `KILLSWITCH.md` (status: halt) or `intent.md` status: halt or
  a tombstoned root note. Checked every loop and before every write.

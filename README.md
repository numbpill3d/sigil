# SIGIL

> vault-native semi-autonomous agent framework

SIGIL's memory substrate is an Obsidian/markdown vault — not a vector DB, not
RAG. The agent "thinks" by walking `[[wikilinks]]` through the vault graph
(link-walk context assembly), and every belief is provenance-stamped,
decay-aged, and conflict-resolved by trust tier. The vault is also the
autonomy control surface: `intent.md` gates every write, proposals require
human approval, and a markdown edit stops the agent.

## Why

See [docs/WHY-NOT-RAG.md](docs/WHY-NOT-RAG.md). Short version: memory you can
read, edit, audit, and trust — instead of a bag of embeddings you can't argue
with.

## Install (dev)

    cd ~/sigil
    python3 -m venv .venv
    . .venv/bin/activate
    pip install -e .
    pip install pytest
    pytest -q          # 79 tests, all green

## Quick start

    sigil hatch --target /tmp/my-agent --fresh       # greenfield vault
    sigil hatch --target /tmp/notes    --adopt       # adopt a tree (secrets filtered)
    sigil walk  --target /tmp/my-agent --note BOOTSTRAP --explain   # inspect context
    sigil chat  --target /tmp/my-agent --note BOOTSTRAP            # run provider
    sigil halt  --target /tmp/my-agent                            # kill-switch

Defaults to `NullProvider` (deterministic echo, no tokens). Set
`OPENROUTER_API_KEY` + `--model openai/gpt-4o-mini` for a real model.

## Docs

- [docs/QUICKSTART.md](docs/QUICKSTART.md) — install, hatch, chat, walk, halt
- [docs/CONCEPTS.md](docs/CONCEPTS.md) — notes, link-walk, provenance, conflict, persona, autonomy
- [docs/WHY-NOT-RAG.md](docs/WHY-NOT-RAG.md) — design rationale vs RAG

## Modules

    sigil/frontmatter.py   YAML frontmatter parse/emit (PyYAML)
    sigil/vault.py         scan -> LinkGraph, path confinement, incremental index
    sigil/provider.py      ModelProvider (Null + OpenRouter)
    sigil/lock.py          atomic write + fcntl + intent allowlist gate
    sigil/hatch.py         GERMINATE / INCUBATE + secret filter
    sigil/context.py       ContextAssembler (link-walk + decay + cache + token cap)
    sigil/provenance.py    per-write provenance stamp
    sigil/conflict.py      claim conflict protocol (human>agent>ingested)
    sigil/persona.py       persona synthesis from persona.md
    sigil/autonomy.py      intent gate, tiers, proposal/approval, kill-switch
    sigil/cli.py           hatch / chat / walk / halt

## Status

v1 complete: the 6 features (link-walk, decay, conflict, persona, provenance,
loose-incubate) + 3 architecture must-haves (incremental scan, context cache,
write lock) + autonomy scaffold + security basics. Phase 2 (deferred, see
plan): daemon heartbeat loop, `delegate` tier + sandbox, federation `share:`,
executable `run` notes (sandboxed), drift detection, fsnotify inbox.

## Safety

SIGIL never walks `~`. Hatch refuses home/root targets. Ingested markdown is
untrusted data — ```` ```run ```` blocks are surfaced as text, never executed.
The intent gate is a code-level allowlist enforced in the write path.

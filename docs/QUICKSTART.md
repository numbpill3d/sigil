# SIGIL — Quickstart

SIGIL is a vault-native agent framework: the agent's memory IS an Obsidian/
markdown vault. No vector DB, no RAG. Context is assembled by walking
`[[wikilinks]]` through the vault graph.

## Install (dev)

    cd ~/sigil
    python3 -m venv .venv
    . .venv/bin/activate
    pip install -e .
    pip install pytest
    pytest -q

## Hatch a vault

    sigil hatch --target ~/my-agent --fresh      # greenfield
    sigil hatch --target ~/existing-notes --adopt # adopt a tree (secrets filtered)

This writes `intent.md`, `persona.md`, `BOOTSTRAP.md`, `MOC.md`,
`schedule.md`, and creates `.obsidian/`.

## Chat

    sigil chat --target ~/my-agent --note BOOTSTRAP

Assembles link-walk context from `BOOTSTRAP.md`, renders the persona system
prompt, and runs the provider. Defaults to `NullProvider` (echo, no tokens).
Set `OPENROUTER_API_KEY` + `--model openai/gpt-4o-mini` for a real model.

## Walk (inspect context)

    sigil walk --target ~/my-agent --note BOOTSTRAP --explain

Prints each note the link-walk would surface, with score / hop / source.
Use this to SEE why the agent thinks what it thinks.

## Stop an agent

    sigil halt --target ~/my-agent

Writes `KILLSWITCH.md` (status: halt). The agent checks this every loop and
before every write. Remove the file (or set `intent.md` status: live) to
resume. A markdown edit is the kill-switch.

## Config

The last `--target` is remembered in `~/.sigil/config.json`, so you can omit
it on later calls.

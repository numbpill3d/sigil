"""SIGIL command-line interface.

Subcommands:
  hatch --target DIR (--fresh | --adopt)   create or adopt a vault
  chat  --target DIR [--note STEM]         assemble context + run provider
  walk  --target DIR --note STEM [--explain]   show link-walk context
  halt  --target DIR                        write KILLSWITCH.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import hatch as hatchmod
from .vault import Vault
from .provider import NullProvider, OpenRouterProvider, ModelProvider
from .context import ContextAssembler
from .persona import load_persona
from . import autonomy as auto
from . import daemon as daemonmod
from . import tui as tui

CONFIG_PATH = os.path.expanduser("~/.sigil/config.json")
C_BRAIN = "▰"


def _load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            return json.load(open(CONFIG_PATH, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    json.dump(cfg, open(CONFIG_PATH, "w", encoding="utf-8"))


def _provider(args, cfg) -> ModelProvider:
    if args.model or os.environ.get("OPENROUTER_API_KEY"):
        try:
            return OpenRouterProvider(model=args.model or "openai/gpt-4o-mini")
        except ValueError:
            pass
    return NullProvider()


def _vault(target, args):
    from . import federation as fedmod
    v = Vault(target)
    shares = getattr(args, "share", None) or []
    if shares:
        remotes = {os.path.basename(s.rstrip("/")): Vault(s) for s in shares}
        fv = fedmod.FederatedVault(v, remotes)
        fv.scan()
        return fv
    v.scan()
    return v


def _resolve_note_or_error(vault, raw_note: str):
    key = vault.resolve_note_key(raw_note) if hasattr(vault, "resolve_note_key") else raw_note
    return key


def cmd_hatch(args, cfg) -> int:
    target = args.target or cfg.get("target")
    if not target:
        print("error: --target required", file=sys.stderr)
        return 2
    tui.echo(tui.banner())
    tui.echo(tui.rule())
    mode = "fresh" if args.fresh else ("adopt" if args.adopt else "fresh")
    with tui.Spinner(f"hatching vault ({mode}) -> {target}"):
        rep = hatchmod.hatch(target, mode)
    cfg["target"] = rep["root"]
    _save_config(cfg)
    tui.note(f"hatched ({rep.get('mode', mode)}) -> {rep['root']}", "g")
    if "copied" in rep:
        tui.note(f"copied {len(rep['copied'])} notes, excluded {len(rep['excluded'])}", "x")
    return 0


def cmd_chat(args, cfg) -> int:
    target = args.target or cfg.get("target")
    if not target or not os.path.isdir(target):
        print("error: no valid --target", file=sys.stderr)
        return 2
    if auto.is_halted(target):
        print("agent halted (kill-switch active). remove KILLSWITCH.md / intent status.", file=sys.stderr)
        return 3
    provider = _provider(args, cfg)
    tui.echo(tui.banner())
    tui.echo(tui.rule())
    vault = _vault(target, args)
    active_raw = args.note or "BOOTSTRAP"
    active = _resolve_note_or_error(vault, active_raw)
    if not active:
        print(f"error: note {active_raw} not found", file=sys.stderr)
        return 2
    assembler = ContextAssembler(vault, provider)
    tui.thinking(f"assembling context from [[{active_raw}]]", seconds=0.9)
    with tui.Spinner(f"consulting {provider.__class__.__name__}"):
        ctx = assembler.assemble(active, k=args.k, hops=args.hops, task_tag=args.task)
        persona = load_persona(target)
        sys_prompt = persona.system_prompt()
        joined = sys_prompt + "\n\n# Assembled context (link-walk):\n" + "\n---\n".join(
            f"[[{n.label}]] (score={n.score:.3f})\n{n.body}" for n in ctx
        )
        out = provider.complete(joined)
    tui.echo(tui.rule())
    pal = tui._pal()
    tui.echo(f"{pal['c']}{C_BRAIN} response{pal['reset']}")
    tui.echo(out)
    tui.echo(tui.rule())
    return 0


def cmd_tui(args, cfg) -> int:
    target = args.target or cfg.get("target")
    if not target or not os.path.isdir(target):
        print("error: no valid --target (run `sigil hatch` first)", file=sys.stderr)
        return 2
    tui.echo(tui.banner())
    tui.echo(tui.rule())
    if auto.is_halted(target):
        tui.note("agent halted — kill-switch active", "r")
        return 3
    vault = _vault(target, args)
    active_raw = args.note or "BOOTSTRAP"
    active = _resolve_note_or_error(vault, active_raw)
    if not active:
        print(f"error: note {active_raw} not found", file=sys.stderr)
        return 2
    with tui.Spinner("loading vault + link graph"):
        assembler = ContextAssembler(vault, NullProvider())
        ctx = assembler.assemble(active, k=args.k, hops=args.hops, task_tag=args.task)
    tui.note(f"active note: [[{active_raw}]]  ·  {len(ctx)} notes in context", "c")
    tui.echo(tui.rule())
    tui.echo(tui.walk_table([{"stem": n.stem, "label": n.label, "score": n.score,
                               "hop": n.hop, "source": n.source,
                               "via": n.via, "parent": n.parent} for n in ctx]))
    tui.echo(tui.rule())
    tui.thinking("agent idle — edit notes to shift context", seconds=1.0)
    tui.note("tip: `sigil chat --target <vault> --model <model>` to talk", "x")
    return 0


def cmd_walk(args, cfg) -> int:
    target = args.target or cfg.get("target")
    if not target or not os.path.isdir(target):
        print("error: no valid --target", file=sys.stderr)
        return 2
    vault = _vault(target, args)
    active = _resolve_note_or_error(vault, args.note)
    if not active:
        print(f"error: note {args.note} not found", file=sys.stderr)
        return 2
    assembler = ContextAssembler(vault, NullProvider())
    with tui.Spinner(f"walking link graph from [[{args.note}]]"):
        ctx = assembler.assemble(active, k=args.k, hops=args.hops, task_tag=args.task)
    tui.echo(tui.rule())
    if args.explain:
        tui.echo(tui.walk_table([{"stem": n.stem, "label": n.label, "score": n.score,
                                   "hop": n.hop, "source": n.source,
                                   "via": n.via, "parent": n.parent} for n in ctx]))
    else:
        tui.echo("  " + tui._pal()["w"] + ", ".join(n.label for n in ctx) + tui._pal()["reset"])
    tui.echo(tui.rule())
    return 0


def cmd_run_note(args, cfg) -> int:
    target = args.target or cfg.get("target")
    if not target or not os.path.isdir(target):
        print("error: no valid --target", file=sys.stderr)
        return 2
    if auto.is_halted(target):
        print("agent halted (kill-switch active).", file=sys.stderr)
        return 3
    from . import runbook as runbookmod
    vault = _vault(target, args)
    note_key = _resolve_note_or_error(vault, args.note)
    if not note_key or note_key not in vault.graph.notes:
        print(f"error: note {args.note} not found", file=sys.stderr)
        return 2
    note_path = vault.graph.notes[note_key].path
    intent = auto.load_intent(target)
    gate = auto.gate_from_intent(intent)
    res = runbookmod.execute_run(note_path, intent, gate=gate)
    if not res["allowed"]:
        print("run not allowed by intent (add 'run' to intent.allowed to opt in).")
        print("--- blocks surfaced as data ---")
        for b in runbookmod.extract_run_blocks(open(note_path, encoding="utf-8").read()):
            print(b)
        return 0
    for o in res["outputs"]:
        print(o)
    if res["errors"]:
        print("errors:", "; ".join(res["errors"]), file=sys.stderr)
    return 0


def cmd_halt(args, cfg) -> int:
    target = args.target or cfg.get("target")
    if not target:
        print("error: --target required", file=sys.stderr)
        return 2
    path = auto.halt(target, reason=args.reason or "")
    print(f"halted. wrote {path}")
    return 0


def cmd_run(args, cfg) -> int:
    target = args.target or cfg.get("target")
    if not target or not os.path.isdir(target):
        print("error: no valid --target", file=sys.stderr)
        return 2
    if auto.is_halted(target):
        print("agent halted (kill-switch active). remove KILLSWITCH.md / intent status.", file=sys.stderr)
        return 3
    if args.daemon:
        import threading
        stop = threading.Event()
        print(f"daemon running on {target} (interval {args.interval}s). ctrl-c to stop.")
        try:
            daemonmod.run_daemon(target, interval=args.interval, stop_event=stop, watch=True)
        except KeyboardInterrupt:
            stop.set()
        return 0
    results = daemonmod.run_due_jobs(target)
    for r in results:
        print(f"{r['target']}: {r['result']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sigil", description="vault-native agent")
    try:
        from importlib.metadata import version as _v
        _ver = _v("sigil")
    except Exception:
        _ver = "dev"
    p.add_argument("--version", action="version", version=f"sigil {_ver}")
    p.add_argument("--ansi", action="store_true",
                   help="force color + animations even when piped (for demos)")
    sub = p.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("hatch")
    h.add_argument("--target")
    g = h.add_mutually_exclusive_group()
    g.add_argument("--fresh", action="store_true")
    g.add_argument("--adopt", action="store_true")
    h.set_defaults(func=cmd_hatch)

    c = sub.add_parser("chat")
    c.add_argument("--target")
    c.add_argument("--note", default="BOOTSTRAP")
    c.add_argument("--k", type=int, default=10)
    c.add_argument("--hops", type=int, default=2)
    c.add_argument("--task")
    c.add_argument("--model")
    c.add_argument("--share", action="append", default=[], help="remote vault path to federate (repeatable)")
    c.set_defaults(func=cmd_chat)

    w = sub.add_parser("walk")
    w.add_argument("--target")
    w.add_argument("--note", required=True)
    w.add_argument("--k", type=int, default=10)
    w.add_argument("--hops", type=int, default=2)
    w.add_argument("--task")
    w.add_argument("--explain", action="store_true")
    w.add_argument("--share", action="append", default=[], help="remote vault path to federate (repeatable)")
    w.set_defaults(func=cmd_walk)

    t = sub.add_parser("tui")
    t.add_argument("--target")
    t.add_argument("--note", default="BOOTSTRAP")
    t.add_argument("--k", type=int, default=10)
    t.add_argument("--hops", type=int, default=2)
    t.add_argument("--task")
    t.add_argument("--share", action="append", default=[], help="remote vault path to federate (repeatable)")
    t.set_defaults(func=cmd_tui)

    rn = sub.add_parser("run-note")
    rn.add_argument("--target")
    rn.add_argument("--note", required=True)
    rn.set_defaults(func=cmd_run_note)

    halt = sub.add_parser("halt")
    halt.add_argument("--target")
    halt.add_argument("--reason")
    halt.set_defaults(func=cmd_halt)

    run = sub.add_parser("run")
    run.add_argument("--target")
    run.add_argument("--daemon", action="store_true")
    run.add_argument("--interval", type=float, default=30.0)
    run.set_defaults(func=cmd_run)
    return p


def main(argv=None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    if getattr(args, "ansi", False):
        os.environ["SIGIL_FORCE_ANSI"] = "1"
    cfg = _load_config()
    return args.func(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())

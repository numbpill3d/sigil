"""SIGIL command-line interface.

Subcommands:
  hatch --target DIR (--fresh | --adopt)   create or adopt a vault
  chat  --target DIR [--note STEM]         assemble context + run provider
  walk  --target DIR --note STEM [--explain]   show link-walk context
  halt  --target DIR                        write KILLSWITCH.md

Config (~/.sigil/config): remembers the last --target so you can omit it.
Provider defaults to NullProvider (no tokens); set OPENROUTER_API_KEY +
--model to use OpenRouter.

The CLI never walks ~/ : every --target is refused if it resolves to home
(see sigil.hatch.HatchError). All writes route through sigil.lock so the
intent gate applies.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import hatch as hatchmod
from .vault import Vault
from .provider import NullProvider, OpenRouterProvider
from .context import ContextAssembler
from .persona import load_persona
from . import autonomy as auto

CONFIG_PATH = os.path.expanduser("~/.sigil/config.json")


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


def _provider(args, cfg) -> object:
    if args.model or os.environ.get("OPENROUTER_API_KEY"):
        try:
            return OpenRouterProvider(model=args.model or "openai/gpt-4o-mini")
        except ValueError:
            pass
    return NullProvider()


def cmd_hatch(args, cfg) -> int:
    target = args.target or cfg.get("target")
    if not target:
        print("error: --target required", file=sys.stderr)
        return 2
    mode = "fresh" if args.fresh else ("adopt" if args.adopt else "fresh")
    rep = hatchmod.hatch(target, mode)
    cfg["target"] = rep["root"]
    _save_config(cfg)
    print(f"hatched ({rep.get('mode', mode)}) -> {rep['root']}")
    if "copied" in rep:
        print(f"  copied {len(rep['copied'])} notes, excluded {len(rep['excluded'])}")
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
    vault = Vault(target)
    vault.scan()
    active = args.note or "BOOTSTRAP"
    assembler = ContextAssembler(vault, provider)
    ctx = assembler.assemble(active, k=args.k, hops=args.hops, task_tag=args.task)
    persona = load_persona(target)
    sys_prompt = persona.system_prompt()
    joined = sys_prompt + "\n\n# Assembled context (link-walk):\n" + "\n---\n".join(
        f"[[{n.stem}]] (score={n.score:.3f})\n{n.body}" for n in ctx
    )
    out = provider.complete(joined)
    print(out)
    return 0


def cmd_walk(args, cfg) -> int:
    target = args.target or cfg.get("target")
    if not target or not os.path.isdir(target):
        print("error: no valid --target", file=sys.stderr)
        return 2
    vault = Vault(target)
    vault.scan()
    assembler = ContextAssembler(vault, NullProvider())
    ctx = assembler.assemble(args.note, k=args.k, hops=args.hops, task_tag=args.task)
    if args.explain:
        for n in ctx:
            print(f"{n.stem:20s} score={n.score:.3f} hop={n.hop} src={n.source}")
    else:
        print(", ".join(n.stem for n in ctx))
    return 0


def cmd_halt(args, cfg) -> int:
    target = args.target or cfg.get("target")
    if not target:
        print("error: --target required", file=sys.stderr)
        return 2
    path = auto.halt(target, reason=args.reason or "")
    print(f"halted. wrote {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sigil", description="vault-native agent")
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
    c.set_defaults(func=cmd_chat)

    w = sub.add_parser("walk")
    w.add_argument("--target")
    w.add_argument("--note", required=True)
    w.add_argument("--k", type=int, default=10)
    w.add_argument("--hops", type=int, default=2)
    w.add_argument("--task")
    w.add_argument("--explain", action="store_true")
    w.set_defaults(func=cmd_walk)

    k = sub.add_parser("halt")
    k.add_argument("--target")
    k.add_argument("--reason", default="")
    k.set_defaults(func=cmd_halt)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = _load_config()
    return args.func(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())

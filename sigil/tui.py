"""TUI / presentation layer (pure stdlib, no extra deps).

The engine stays stdlib-first and headless; this module only handles
*looks*: an unusual hand-drawn ASCII wordmark for SIGIL, an ANSI color
palette, a spinner, and a "thinking" animation. Everything degrades to
plain static output when stdout is not a TTY (piped / captured), so the
CLI stays scriptable.

Design note: we deliberately do NOT pull in `rich` or `pyfiglet` to keep
the dependency surface at PyYAML only. The wordmark is hand-authored in a
non-default style (slanted half-block + bracket frame) rather than a
figlet default font.
"""

from __future__ import annotations

import sys
import time
from typing import Iterable, Optional

# ---- color palette (truecolor ANSI) --------------------------------------
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITAL = "\033[3m"
    # foreground truecolor helpers
    @staticmethod
    def fg(r: int, g: int, b: int) -> str:
        return f"\033[38;2;{r};{g};{b}m"
    @staticmethod
    def bg(r: int, g: int, b: int) -> str:
        return f"\033[48;2;{r};{g};{b}m"


# sigil accent gradient (violet -> cyan)
VIOLET = C.fg(170, 120, 255)
CYAN = C.fg(90, 220, 230)
PINK = C.fg(255, 130, 200)
GREEN = C.fg(120, 230, 150)
AMBER = C.fg(255, 200, 90)
GREY = C.fg(140, 150, 170)
WHITE = C.fg(230, 235, 245)
RED = C.fg(255, 110, 110)


def _color_on() -> bool:
    return sys.stdout.isatty()


def _pal() -> dict:
    """Return a palette that is either colored or plain based on TTY."""
    if _color_on():
        return {
            "v": VIOLET, "c": CYAN, "p": PINK, "g": GREEN,
            "a": AMBER, "x": GREY, "w": WHITE, "r": RED,
            "b": C.BOLD, "d": C.DIM, "i": C.ITAL, "reset": C.RESET,
        }
    return {k: "" for k in "vcpgaxwbrdi"} | {"reset": ""}


# ---- unusual hand-authored wordmark (not a default figlet font) ---------
# slanted half-block style with a bracket frame. each line is pre-spaced.
SIGIL_ART = r"""
 ___       _       _    ___ _
/ __|  ___| |_ _ _(_)  / __| |_ _ _ ___ __ _ _ __
\__ \ / -_)  _| '_| |  \__ \  _| '_/ -_) _` | '  \
|___/ \___|\__|_| |_|  |___/\__|_| \___\__,_|_|_|_|
"""


def banner(subtitle: str = "vault-native agent") -> str:
    pal = _pal()
    lines = SIGIL_ART.splitlines(keepends=True)
    out = []
    for i, ln in enumerate(lines):
        # gradient sweep violet -> cyan across the lines
        col = VIOLET if i < 2 else (CYAN if i == 2 else PINK)
        out.append(f"{col}{C.BOLD}{ln}{C.RESET}")
    tag = f"{pal['x']}{C.DIM}  {subtitle}{C.RESET}\n"
    out.append(tag)
    return "".join(out)


# ---- spinner -------------------------------------------------------------
_SPIN_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_DOT_FRAMES = ["   ", ".  ", ".. ", "..."]


class Spinner:
    """Context manager that shows a live spinner + label, then a result.

    Usage:
        with Spinner("scanning vault"):
            do_work()
        # prints:  ✓ scanning vault  (on clean exit)

    In non-TTY mode it prints the label once and nothing animated.
    """

    def __init__(self, label: str, color: str = "", success: str = "✓",
                 fail: str = "✗"):
        self.label = label
        self.color = color or VIOLET
        self.success = success
        self.fail = fail
        self._tick = 0
        self._alive = False

    def _render(self, frame: str) -> None:
        pal = _pal()
        sys.stdout.write(
            f"\r{pal['b']}{self.color}{frame}{pal['reset']} "
            f"{self.label} {pal['reset']}"
        )
        sys.stdout.flush()

    def _clear(self) -> None:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def __enter__(self):
        if _color_on():
            self._alive = True
            self._render(_SPIN_FRAMES[0])
        else:
            sys.stdout.write(f"{self.label} ...\n")
            sys.stdout.flush()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._alive = False
        pal = _pal()
        if exc_type:
            self._clear()
            sys.stdout.write(
                f"{pal['r']}{self.fail}{pal['reset']} {self.label}\n"
            )
            sys.stdout.flush()
        else:
            self._clear()
            sys.stdout.write(
                f"{pal['g']}{self.success}{pal['reset']} {self.label}\n"
            )
            sys.stdout.flush()
        return False  # don't suppress exceptions


def thinking(label: str = "thinking", seconds: float = 1.2,
             frames: Optional[Iterable[str]] = None) -> None:
    """Show a short 'thinking' animation for `seconds`, then clear the line.

    Non-TTY: prints the label once, no animation.
    """
    pal = _pal()
    seq = list(frames) if frames else _DOT_FRAMES
    if not _color_on():
        sys.stdout.write(f"{label}...\n")
        sys.stdout.flush()
        return
    end = time.time() + seconds
    i = 0
    try:
        while time.time() < end:
            f = seq[i % len(seq)]
            sys.stdout.write(
                f"\r{pal['v']}{C.BOLD}{label}{pal['reset']} "
                f"{pal['x']}{f}{pal['reset']}"
            )
            sys.stdout.flush()
            time.sleep(0.18)
            i += 1
    finally:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


def rule(width: int = 54, char: str = "─") -> str:
    pal = _pal()
    return f"{pal['x']}{C.DIM}{char * width}{C.RESET}"


def kv(key: str, val: str, kw: str = "v") -> str:
    pal = _pal()
    return f"  {pal[kw]}{C.BOLD}{key}{pal['reset']}  {pal['w']}{val}{pal['reset']}"


def note(msg: str, kind: str = "x") -> None:
    pal = _pal()
    prefix = {"x": "·", "g": "✓", "r": "✗", "a": "!", "c": "→"}.get(kind, "·")
    col = {"x": GREY, "g": GREEN, "r": RED, "a": AMBER, "c": CYAN}.get(kind, GREY)
    sys.stdout.write(f"{pal['b']}{col}{prefix}{pal['reset']} {pal['w']}{msg}{pal['reset']}\n")
    sys.stdout.flush()


def walk_table(rows: list) -> str:
    """Pretty colored table for walk --explain output.

    rows: list of dicts with stem, score, hop, source
    """
    pal = _pal()
    if not rows:
        return f"{pal['x']}{C.DIM}  (no notes reached){C.RESET}\n"
    head = f"  {pal['x']}{C.DIM}{'note'.ljust(20)} {'score'.rjust(7)} {'hop'.rjust(4)} {'source'.rjust(7)}{C.RESET}\n"
    body = []
    for r in rows:
        score = float(r.get("score", 0.0))
        # color by score
        scol = GREEN if score >= 0.75 else (AMBER if score >= 0.5 else GREY)
        src = r.get("source", "agent")
        srccol = CYAN if src == "human" else VIOLET
        body.append(
            f"  {pal['w']}{str(r.get('stem',''))[:20].ljust(20)} "
            f"{pal['b']}{scol}{f'{score:.3f}'.rjust(7)} "
            f"{pal['x']}{str(r.get('hop','0')).rjust(4)} "
            f"{pal['b']}{srccol}{src.rjust(7)}{pal['reset']}"
        )
    return head + "\n".join(body) + "\n"


def echo(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()

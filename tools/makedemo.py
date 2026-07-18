"""Demo GIF generator (no external TTY recorder needed).

Renders real SIGIL TUI frames to animated GIFs using the bundled tui
helpers + ImageMagick (`convert`). Each animation frame is a composed
screen string (banner + rule + body + animated line) with truecolor ANSI,
rendered to a PNG, then all frames stitched into a looping GIF.

Usage:
    python tools/makedemo.py            # writes docs/assets/demo_*.gif
    SIGIL_ANSI=1 python tools/makedemo.py

Requires `convert` (ImageMagick) on PATH.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil import tui as T


SPIN = list("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
DOTS = ["   ", ".  ", ".. ", "..."]


def _render_png(text: str, path: str, width: int = 760, fontsize: int = 17) -> None:
    """Render an ANSI-colored string to a PNG via ImageMagick."""
    # strip trailing newline; convert interprets \n as line breaks in label:
    cmd = [
        "convert", "-background", "#0d1117", "-fill", "#c9d1d9",
        "-font", "DejaVu-Sans-Mono", "-pointsize", str(fontsize),
        "-size", f"{width}x",
        f"label:{text}", path,
    ]
    subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)


def _frames_to_gif(frames: list[str], out_path: str, delay: int = 12) -> None:
    """Render each frame to a temp PNG, then combine into a GIF."""
    tmp = tempfile.mkdtemp(prefix="sigil-demo-")
    pngs = []
    for i, fr in enumerate(frames):
        p = os.path.join(tmp, f"f{i:03d}.png")
        _render_png(fr, p)
        pngs.append(p)
    cmd = ["convert", "-loop", "0", "-delay", str(delay)] + pngs + [out_path]
    subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
    for p in pngs:
        os.remove(p)
    os.rmdir(tmp)


def demo_hatch() -> list[str]:
    """Frames for `sigil hatch --fresh`: banner + spinner -> done note."""
    frames = []
    base = [T.banner(), T.rule()]
    for s in SPIN:
        frames.append(T.screen(*base, T.spinner_line("hatching vault (fresh) -> ~/sigil-brain", s)))
    done = T.screen(
        *base,
        T.spinner_line("hatching vault (fresh) -> ~/sigil-brain", "✓").replace("✓", "✓"),
        "",
        T.note("hatched (germinate) -> ~/sigil-brain", "g") if False else "  \033[1m\033[38;2;120;230;150m✓ hatched (germinate) -> ~/sigil-brain\033[0m",
    )
    frames.append(done)
    return frames


def demo_tui() -> list[str]:
    """Frames for `sigil tui`: banner + spinner -> walk table -> thinking."""
    frames = []
    base = [T.banner(), T.rule()]
    for s in SPIN:
        frames.append(T.screen(*base, T.spinner_line("loading vault + link graph", s)))
    rows = [
        {"stem": "BOOTSTRAP", "score": 0.900, "hop": 0, "source": "agent"},
        {"stem": "MOC", "score": 0.750, "hop": 1, "source": "agent"},
        {"stem": "example", "score": 0.750, "hop": 1, "source": "agent"},
        {"stem": "persona", "score": 0.600, "hop": 2, "source": "human"},
        {"stem": "intent", "score": 0.600, "hop": 2, "source": "human"},
    ]
    loaded = T.screen(
        *base,
        "  \033[1m\033[38;2;90;220;230m→ active note: [[BOOTSTRAP]]  ·  5 notes in context\033[0m",
        T.rule(),
        T.walk_table(rows),
        T.rule(),
    )
    frames.append(loaded)
    for d in DOTS:
        frames.append(T.screen(loaded, T.thinking_line("agent idle — edit notes to shift context", d)))
    return frames


def demo_chat() -> list[str]:
    """Frames for `sigil chat`: banner + thinking -> spinner -> response."""
    frames = []
    base = [T.banner(), T.rule()]
    for d in DOTS:
        frames.append(T.screen(*base, T.thinking_line("assembling context from [[BOOTSTRAP]]", d)))
    for s in SPIN:
        frames.append(T.screen(*base, T.spinner_line("consulting NullProvider", s)))
    resp = T.screen(
        *base,
        "  \033[1m\033[38;2;90;220;230m▰ response\033[0m",
        "  [null-provider-echo]",
        "  # Persona",
        "  voice: direct, lowercase, no fluff",
        "  # Assembled context (link-walk):",
        "  [[BOOTSTRAP]] (score=0.900)",
        "  this vault is the memory and mind of a sigil agent.",
        T.rule(),
    )
    frames.append(resp)
    return frames


def main() -> int:
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "docs", "assets")
    os.makedirs(out_dir, exist_ok=True)
    T.FORCE_ANSI = True
    jobs = {
        "demo_hatch.gif": demo_hatch,
        "demo_tui.gif": demo_tui,
        "demo_chat.gif": demo_chat,
    }
    for name, fn in jobs.items():
        out = os.path.join(out_dir, name)
        frames = fn()
        _frames_to_gif(frames, out, delay=14)
        print(f"wrote {out} ({len(frames)} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

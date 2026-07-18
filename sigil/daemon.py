"""Daemon heartbeat loop (Phase 2, P2-1).

v1 shipped `heartbeat_once()` (runs due schedule lines once, note
read/write only) + the `schedule.md` template + its unit test, but NO
long-running loop. This module adds `sigil run --daemon`: a loop that

  - re-reads intent.md EVERY iteration (so live intent edits take effect),
  - checks `is_halted()` BEFORE every job (markdown kill-switch wins),
  - parses `schedule.md` cron-like lines and runs only DUE ones,
  - sleeps `interval` seconds between iterations,
  - exits cleanly on kill-switch or a stop Event (testable without real time).

The loop never executes code. A "job" is a schedule line `<cron> | <note>`;
the only effect is reading/touching/creating the named note. Executable
`run` notes remain phase 2 (P2-4) and are surfaced as data, never run here.

Time source is injectable (`now_fn`) so tests are deterministic and fast.
"""

from __future__ import annotations

import os
import re
import time
from typing import Callable, Optional

from . import autonomy as auto
from .autonomy import heartbeat_once

# crude 5-field cron matcher: supports */n, *, and exact values per field
# fields: minute hour day-of-month month day-of-week
_CRON_RE = re.compile(r"^\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*\|?\s*(.*)$")


def _field_match(spec: str, val: int) -> bool:
    if spec == "*":
        return True
    if spec.startswith("*/"):
        step = int(spec[2:])
        return val % step == 0
    try:
        return int(spec) == val
    except ValueError:
        return False


def _cron_due(expr: str, now: time.struct_time) -> bool:
    """Return True if the 5-field cron expression matches `now`."""
    parts = expr.split()
    if len(parts) < 5:
        return False
    m, h, dom, mon, dow = parts[:5]
    # dow: 0=Mon..6=Sun or 7=Sun; struct_time tm_wday is 0=Mon..6=Sun
    return (
        _field_match(m, now.tm_min)
        and _field_match(h, now.tm_hour)
        and _field_match(dom, now.tm_mday)
        and _field_match(mon, now.tm_mon)
        and _field_match(dow, now.tm_wday)
    )


def parse_schedule(path: str) -> list:
    """Parse schedule.md into [(cron_expr, target, raw_line), ...]."""
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding="utf-8").read().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _CRON_RE.match(line)
        if not m:
            continue
        cron = " ".join(m.group(1, 2, 3, 4, 5))
        target = m.group(6).strip() or m.group(5).strip()
        out.append((cron, target, line))
    return out


def run_due_jobs(
    vault_root: str,
    now_fn: Callable[[], float] = time.time,
) -> list:
    """Run due jobs from schedule.md once. Returns the heartbeat_once results.

    Re-loads intent, checks halt BEFORE acting. No-op if halted.
    """
    if auto.is_halted(vault_root):
        return []
    sched_path = os.path.join(vault_root, "schedule.md")
    jobs = parse_schedule(sched_path)
    if not jobs:
        return []
    now = time.localtime(now_fn())
    due = [raw for (cron, target, raw) in jobs if _cron_due(cron, now)]
    if not due:
        return []
    sched_text = "\n".join(due) + "\n"
    return heartbeat_once(vault_root, sched_text)


def run_daemon(
    vault_root: str,
    interval: float = 1.0,
    stop_event=None,
    now_fn: Callable[[], float] = time.time,
    max_iter: Optional[int] = None,
) -> int:
    """Long-running loop. Returns iteration count.

    `stop_event` is a threading.Event (or any object with `.is_set()`); if
    set, the loop exits. `max_iter` bounds iterations for tests. Halt is
    checked every iteration before running jobs.
    """
    vault_root = os.path.realpath(vault_root)
    iterations = 0
    while True:
        if stop_event is not None and stop_event.is_set():
            break
        if auto.is_halted(vault_root):
            break
        run_due_jobs(vault_root, now_fn=now_fn)
        iterations += 1
        if max_iter is not None and iterations >= max_iter:
            break
        if stop_event is not None:
            # wait but wake on stop
            stop_event.wait(interval)
        else:
            time.sleep(interval)
    return iterations

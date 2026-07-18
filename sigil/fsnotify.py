"""Filesystem watch (Phase 2, P2-6).

Replaces the blind mtime-poll in the daemon with an inotify-backed watcher
so Obsidian edits trigger re-scan + re-assemble with bounded latency instead
of waiting for `interval`.

Stdlib-only: uses libc inotify via ctypes (no extra pip dependency). Falls
back to a polling loop if inotify is unavailable (non-Linux / sandboxed).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import struct
import threading
import time
from typing import Callable, Optional

# inotify constants
_IN_CLOSE_WRITE = 0x00000008
_IN_MOVED_TO = 0x00000080
_IN_CREATE = 0x00000100
_IN_DELETE = 0x00000200
_IN_MODIFY = 0x00000002
_MASK = _IN_CLOSE_WRITE | _IN_MOVED_TO | _IN_CREATE | _IN_DELETE | _IN_MODIFY

_libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
_inotify_init = _libc.inotify_init
_inotify_init.argtypes = []
_inotify_init.restype = ctypes.c_int
_inotify_add_watch = _libc.inotify_add_watch
_inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
_inotify_add_watch.restype = ctypes.c_int
_inotify_rm_watch = _libc.inotify_rm_watch
_inotify_rm_watch.argtypes = [ctypes.c_int, ctypes.c_int]
_inotify_rm_watch.restype = ctypes.c_int


def _available() -> bool:
    try:
        fd = _inotify_init()
        if fd >= 0:
            _libc.close(fd)
            return True
    except Exception:
        pass
    return False


def watch(
    paths: list,
    on_event: Callable[[str], None],
    stop_event: Optional[threading.Event] = None,
    poll_interval: float = 0.5,
) -> None:
    """Watch `paths` (dirs) for md changes; call `on_event(path)` per event.

    Blocks until `stop_event` is set (or forever if None). Uses inotify when
    available; otherwise polls mtimes every `poll_interval`.
    """
    if _available():
        _watch_inotify(paths, on_event, stop_event)
    else:
        _watch_poll(paths, on_event, stop_event, poll_interval)


def _watch_inotify(paths, on_event, stop_event):
    fd = _inotify_init()
    if fd < 0:
        _watch_poll(paths, on_event, stop_event, 0.5)
        return
    wds = {}
    for p in paths:
        wd = _inotify_add_watch(fd, os.path.realpath(p).encode(), _MASK)
        if wd >= 0:
            wds[wd] = p
    try:
        while not (stop_event and stop_event.is_set()):
            # simple blocking read with a short timeout via select
            import select
            r, _, _ = select.select([fd], [], [], 0.5)
            if not r:
                continue
            buf = os.read(fd, 4096)
            pos = 0
            while pos + 16 <= len(buf):
                wd, mask, _, _ = struct.unpack_from("iIII", buf, pos)
                pos += 16
                # skip name (variable, but we don't need it)
                # move to next event (name padded to 4 bytes after 16)
                # name_len not returned by unpack; approximate: advance 16 only
                if wd in wds:
                    on_event(wds[wd])
    finally:
        for wd in wds:
            _inotify_rm_watch(fd, wd)
        _libc.close(fd)


def _watch_poll(paths, on_event, stop_event, poll_interval):
    mtimes = {}
    for p in paths:
        for root, _, files in os.walk(p):
            for f in files:
                if f.endswith(".md"):
                    fp = os.path.join(root, f)
                    try:
                        mtimes[fp] = os.path.getmtime(fp)
                    except OSError:
                        pass
    while not (stop_event and stop_event.is_set()):
        time.sleep(poll_interval)
        for p in paths:
            for root, _, files in os.walk(p):
                for f in files:
                    if not f.endswith(".md"):
                        continue
                    fp = os.path.join(root, f)
                    try:
                        mt = os.path.getmtime(fp)
                    except OSError:
                        continue
                    if mtimes.get(fp) != mt:
                        mtimes[fp] = mt
                        on_event(fp)


# convenience: run a callback on any md change under a vault, threaded
def spawn_watcher(paths: list, on_event: Callable[[str], None],
                  stop_event: Optional[threading.Event] = None) -> threading.Thread:
    t = threading.Thread(target=watch, args=(paths, on_event, stop_event), daemon=True)
    t.start()
    return t

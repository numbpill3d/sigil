import sys, os, tempfile, shutil, time, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil import fsnotify as F


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def test_inotify_availability_flag():
    # should not raise; returns bool
    assert isinstance(F._available(), bool)


def test_watch_poll_fires_on_md_change(tmp_path):
    d = str(tmp_path)
    _write(os.path.join(d, "a.md"), "hello\n")
    events = []
    stop = threading.Event()
    t = threading.Thread(target=F._watch_poll, args=([d], events.append, stop, 0.05))
    t.start()
    time.sleep(0.1)
    _write(os.path.join(d, "a.md"), "changed\n")
    # give poll loop time
    deadline = time.time() + 2.0
    while not events and time.time() < deadline:
        time.sleep(0.05)
    stop.set()
    t.join(timeout=2)
    assert events, "poll watcher should have fired on md change"


def test_spawn_watcher_triggers_callback(tmp_path):
    d = str(tmp_path)
    _write(os.path.join(d, "b.md"), "x\n")
    hits = []
    stop = threading.Event()
    thr = F.spawn_watcher([d], lambda p: hits.append(p), stop)
    time.sleep(0.2)
    _write(os.path.join(d, "b.md"), "y\n")
    deadline = time.time() + 3.0
    while not hits and time.time() < deadline:
        time.sleep(0.05)
    stop.set()
    thr.join(timeout=2)
    assert hits, "watcher callback should fire on edit"


def test_daemon_with_watch_flag_runs(monkeypatch):
    # just ensure run_daemon accepts watch= and runs at least one iteration
    import tempfile
    from sigil import hatch as hatchmod
    from sigil import daemon as D
    d = tempfile.mkdtemp()
    try:
        hatchmod.hatch(d, "fresh")
        with open(os.path.join(d, "schedule.md"), "w", encoding="utf-8") as fh:
            fh.write("* * * * * | tick\n")
        iters = D.run_daemon(d, interval=0.01, max_iter=3, watch=False)
        assert iters == 3
    finally:
        shutil.rmtree(d, ignore_errors=True)

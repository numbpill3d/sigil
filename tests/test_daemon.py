import sys, os, tempfile, shutil, time as _time, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil import daemon as D
from sigil import autonomy as auto
from sigil import hatch as hatchmod
from sigil.frontmatter import emit


def _write(root, name, text):
    with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
        fh.write(text)


def _hatch():
    d = tempfile.mkdtemp()
    hatchmod.hatch(d, "fresh")
    return d


def test_parse_schedule_skips_comments_and_blanks():
    d = _hatch()
    try:
        _write(d, "schedule.md", "# schedule\n\n0 9 * * * | daily-review\n*/5 * * * * | heartbeat\n")
        jobs = D.parse_schedule(os.path.join(d, "schedule.md"))
        assert len(jobs) == 2
        assert jobs[0][1] == "daily-review"
        assert jobs[1][1] == "heartbeat"
    finally:
        shutil.rmtree(d)


def test_cron_due_exact_match():
    st = _time.struct_time((2026, 7, 18, 9, 0, 0, 5, 199, 0))  # Sat? tm_wday=5
    assert D._cron_due("0 9 * * *", st) is True
    assert D._cron_due("0 10 * * *", st) is False
    assert D._cron_due("*/15 * * * *", st) is True   # 0 % 15 == 0
    assert D._cron_due("*/3 * * * *", st) is True    # 0 % 3 == 0
    assert D._cron_due("* * * * *", st) is True


def test_run_due_jobs_creates_note():
    d = _hatch()
    try:
        # craft a schedule whose cron matches "every minute" so it's always due
        _write(d, "schedule.md", "* * * * * | tick-note\n")
        results = D.run_due_jobs(d, now_fn=lambda: _time.time())
        assert len(results) == 1
        assert results[0]["target"] == "tick-note"
        assert results[0]["result"] in ("created", "touched")
        assert os.path.exists(os.path.join(d, "tick-note.md"))
    finally:
        shutil.rmtree(d)


def test_run_due_jobs_noop_when_halted():
    d = _hatch()
    try:
        _write(d, "schedule.md", "* * * * * | tick-note\n")
        auto.halt(d, "test")
        results = D.run_due_jobs(d, now_fn=lambda: _time.time())
        assert results == []
        assert not os.path.exists(os.path.join(d, "tick-note.md"))
    finally:
        shutil.rmtree(d)


def test_daemon_stops_on_killswitch():
    d = _hatch()
    try:
        _write(d, "schedule.md", "* * * * * | tick-note\n")
        stop = threading.Event()
        # run daemon bounded by max_iter so it doesn't loop forever;
        # but also prove it stops when halted mid-run via a thread
        def _kill():
            _time.sleep(0.05)
            auto.halt(d, "kill")
        killer = threading.Thread(target=_kill)
        killer.start()
        iters = D.run_daemon(d, interval=0.01, stop_event=stop, max_iter=1000)
        killer.join()
        assert iters >= 1  # ran at least one iteration before halt
        # after halt, a fresh run_daemon should exit immediately (0 iters)
        iters2 = D.run_daemon(d, interval=0.01, stop_event=stop, max_iter=1000)
        assert iters2 == 0
    finally:
        shutil.rmtree(d)


def test_daemon_stops_on_stop_event():
    d = _hatch()
    try:
        _write(d, "schedule.md", "* * * * * | tick-note\n")
        stop = threading.Event()
        def _set_stop():
            _time.sleep(0.05)
            stop.set()
        setter = threading.Thread(target=_set_stop)
        setter.start()
        iters = D.run_daemon(d, interval=0.01, stop_event=stop, max_iter=100000)
        setter.join()
        assert iters >= 1
    finally:
        shutil.rmtree(d)

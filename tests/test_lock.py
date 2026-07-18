import sys, os, tempfile, shutil, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil.lock import atomic_write, IntentGate, GateRejected


def test_atomic_write_creates_file():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "note.md")
        atomic_write(p, "# hello\n")
        assert os.path.exists(p)
        assert open(p, encoding="utf-8").read() == "# hello\n"
    finally:
        shutil.rmtree(d)


def test_gate_rejects_forbidden():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "secret.md")
        gate = IntentGate(allowed=["*"], forbidden=["secret"])
        try:
            atomic_write(p, "x", gate=gate, action="write")
            assert False, "expected GateRejected"
        except GateRejected:
            pass
        assert not os.path.exists(p)
    finally:
        shutil.rmtree(d)


def test_gate_allows_when_in_allowed():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "notes/ok.md")
        gate = IntentGate(allowed=["notes/"], forbidden=[])
        atomic_write(p, "fine", gate=gate, action="write")
        assert os.path.exists(p)
    finally:
        shutil.rmtree(d)


def test_gate_rejects_when_not_in_allowed():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "other/x.md")
        gate = IntentGate(allowed=["notes/"], forbidden=[])
        try:
            atomic_write(p, "no", gate=gate, action="write")
            assert False, "expected GateRejected"
        except GateRejected:
            pass
    finally:
        shutil.rmtree(d)


def test_concurrent_writes_no_lost_update():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "shared.md")
        atomic_write(p, "init\n")
        counter = {"n": 0}

        def worker(i):
            for _ in range(20):
                atomic_write(p, f"writer {i} tick\n")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # file must exist and be valid (no truncation / no OSError leaked)
        content = open(p, encoding="utf-8").read()
        assert content.endswith("\n")
        assert len(content.splitlines()) == 1
        # no leftover .tmp files
        assert not any(f.endswith(".tmp") for f in os.listdir(d))
    finally:
        shutil.rmtree(d)

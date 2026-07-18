import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil import runbook as R


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def test_extract_run_blocks_returns_text_only():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "n.md")
        _write(p, "# n\n\n```run\necho hi\n```\n\nbody\n")
        blocks = R.extract_run_blocks(open(p, encoding="utf-8").read())
        assert blocks == ["echo hi"]
        # default: not executed
        res = R.execute_run(p, {"allowed": []})
        assert res["allowed"] is False
        assert res["ran"] is False
        assert res["outputs"] == []
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_execute_runs_when_intent_allows():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "n.md")
        _write(p, "```run\necho hello-world\n```\n")
        res = R.execute_run(p, {"allowed": ["run"]})
        assert res["allowed"] is True
        assert res["ran"] is True
        assert any("hello-world" in o for o in res["outputs"])
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_execute_refuses_without_run_in_intent():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "n.md")
        _write(p, "```run\nrm -rf /\n```\n")
        res = R.execute_run(p, {"allowed": ["*"]})  # * is not "run"
        assert res["ran"] is False
        assert res["errors"] == ["intent does not allow run"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_no_shell_injection():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "n.md")
        # a semicolon must NOT spawn a second command; argv is split literally
        _write(p, "```run\necho a; touch evil\n```\n")
        res = R.execute_run(p, {"allowed": ["run"]})
        assert res["ran"] is True
        # 'touch evil' is treated as a single argument to echo, not executed
        assert any("a; touch evil" in o for o in res["outputs"])
        assert not os.path.exists(os.path.join(d, "evil"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_timeout_kills_long_running():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "n.md")
        _write(p, "```run\nsleep 30\n```\n")
        res = R.execute_run(p, {"allowed": ["run"]}, timeout=0.3)
        assert res["ran"] is True
        assert "timeout" in res["errors"]
    finally:
        shutil.rmtree(d, ignore_errors=True)

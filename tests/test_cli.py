import sys, os, tempfile, shutil, subprocess, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CLI = "-m sigil.cli"


def _run(*args):
    env = dict(os.environ)
    env["HOME"] = tempfile.mkdtemp()  # isolate config
    return subprocess.run(
        [sys.executable, "-m", "sigil.cli", *args],
        capture_output=True, text=True, env=env, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )


def test_cli_hatch_fresh_persists_config():
    home = tempfile.mkdtemp()
    d = tempfile.mkdtemp()
    try:
        env = dict(os.environ)
        env["HOME"] = home
        r = subprocess.run(
            [sys.executable, "-m", "sigil.cli", "hatch", "--target", d, "--fresh"],
            capture_output=True, text=True, env=env,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        assert r.returncode == 0, r.stderr
        assert os.path.exists(os.path.join(d, "intent.md"))
        # config persisted under isolated HOME
        cfg_path = os.path.join(home, ".sigil", "config.json")
        assert os.path.exists(cfg_path)
        cfg = json.load(open(cfg_path))
        assert cfg["target"] == os.path.realpath(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


def test_cli_hatch_refuses_home():
    # directly assert HatchError via the module for a home target
    from sigil.hatch import hatch, HatchError
    try:
        hatch(os.path.expanduser("~"), "fresh")
        assert False, "expected HatchError"
    except HatchError:
        pass


def test_cli_walk_explain_runs():
    d = tempfile.mkdtemp()
    try:
        _run("hatch", "--target", d, "--fresh")
        os.makedirs(os.path.join(d, "projects"), exist_ok=True)
        with open(os.path.join(d, "projects", "sigil.md"), "w", encoding="utf-8") as fh:
            fh.write("---\ntitle: sigil\nsource: human\n---\nbacklinks into [[BOOTSTRAP]]\n")
        r = _run("walk", "--target", d, "--note", "BOOTSTRAP", "--explain")
        assert r.returncode == 0, r.stderr
        assert "BOOTSTRAP" in r.stdout
        assert "via" in r.stdout and "parent" in r.stdout
        assert "projects/sigil" in r.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_walk_accepts_nested_note_path():
    d = tempfile.mkdtemp()
    try:
        _run("hatch", "--target", d, "--fresh")
        os.makedirs(os.path.join(d, "projects"), exist_ok=True)
        with open(os.path.join(d, "projects", "sigil.md"), "w", encoding="utf-8") as fh:
            fh.write("---\ntitle: sigil\nsource: human\n---\nbacklinks into [[BOOTSTRAP]]\n")
        r = _run("walk", "--target", d, "--note", "projects/sigil", "--explain")
        assert r.returncode == 0, r.stderr
        assert "projects/sigil" in r.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_halt_writes_killswitch():
    d = tempfile.mkdtemp()
    try:
        _run("hatch", "--target", d, "--fresh")
        r = _run("halt", "--target", d)
        assert r.returncode == 0, r.stderr
        assert os.path.exists(os.path.join(d, "KILLSWITCH.md"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_chat_runs_with_null_provider():
    d = tempfile.mkdtemp()
    try:
        # ensure NullProvider: no OPENROUTER_API_KEY, no --model
        env = dict(os.environ)
        env.pop("OPENROUTER_API_KEY", None)
        env["HOME"] = tempfile.mkdtemp()
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # hatch first
        h = subprocess.run(
            [sys.executable, "-m", "sigil.cli", "hatch", "--target", d, "--fresh"],
            capture_output=True, text=True, env=env, cwd=cwd,
        )
        assert h.returncode == 0, h.stderr
        r = subprocess.run(
            [sys.executable, "-m", "sigil.cli", "chat", "--target", d, "--note", "BOOTSTRAP"],
            capture_output=True, text=True, env=env, cwd=cwd,
        )
        assert r.returncode == 0, r.stderr
        assert "null-provider-echo" in r.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_run_oneshot_creates_due_note():
    d = tempfile.mkdtemp()
    try:
        env = dict(os.environ)
        env["HOME"] = tempfile.mkdtemp()
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        h = subprocess.run(
            [sys.executable, "-m", "sigil.cli", "hatch", "--target", d, "--fresh"],
            capture_output=True, text=True, env=env, cwd=cwd,
        )
        assert h.returncode == 0, h.stderr
        # write an always-due schedule line
        with open(os.path.join(d, "schedule.md"), "w", encoding="utf-8") as fh:
            fh.write("* * * * * | tick-note\n")
        r = subprocess.run(
            [sys.executable, "-m", "sigil.cli", "run", "--target", d],
            capture_output=True, text=True, env=env, cwd=cwd,
        )
        assert r.returncode == 0, r.stderr
        assert "tick-note" in r.stdout
        assert os.path.exists(os.path.join(d, "tick-note.md"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_run_daemon_flag_accepted():
    d = tempfile.mkdtemp()
    try:
        env = dict(os.environ)
        env["HOME"] = tempfile.mkdtemp()
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        h = subprocess.run(
            [sys.executable, "-m", "sigil.cli", "hatch", "--target", d, "--fresh"],
            capture_output=True, text=True, env=env, cwd=cwd,
        )
        assert h.returncode == 0, h.stderr
        # run daemon with a short interval; it should start then we halt it
        proc = subprocess.Popen(
            [sys.executable, "-m", "sigil.cli", "run", "--target", d, "--daemon", "--interval", "0.01"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=cwd,
        )
        import time as _t
        _t.sleep(0.2)
        # halt via KILLSWITCH -> daemon should exit
        subprocess.run(
            [sys.executable, "-m", "sigil.cli", "halt", "--target", d],
            capture_output=True, text=True, env=env, cwd=cwd,
        )
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            assert False, "daemon did not stop on kill-switch"
        assert proc.returncode == 0
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_run_note_refused_without_intent_run():
    d = tempfile.mkdtemp()
    try:
        _run("hatch", "--target", d, "--fresh")
        # write a note with a run block that would create a side-effect file
        with open(os.path.join(d, "script.md"), "w", encoding="utf-8") as fh:
            fh.write("# script\n\n```run\ntouch sidefile\n```\n")
        r = _run("run-note", "--target", d, "--note", "script")
        assert r.returncode == 0, r.stderr
        # not executed: side-effect file must NOT exist
        assert not os.path.exists(os.path.join(d, "sidefile"))
        assert "not allowed" in r.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_run_note_executes_when_intent_allows():
    d = tempfile.mkdtemp()
    try:
        _run("hatch", "--target", d, "--fresh")
        # opt in: add 'run' to intent.allowed
        intent_path = os.path.join(d, "intent.md")
        txt = open(intent_path, encoding="utf-8").read()
        txt = txt.replace("allowed: [write, propose]", "allowed: [write, propose, run]")
        open(intent_path, "w", encoding="utf-8").write(txt)
        with open(os.path.join(d, "script.md"), "w", encoding="utf-8") as fh:
            fh.write("# script\n\n```run\necho ran-ok\n```\n")
        r = _run("run-note", "--target", d, "--note", "script")
        assert r.returncode == 0, r.stderr
        assert "ran-ok" in r.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)

import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil.hatch import hatch, germinate, incubate, HatchError, _looks_secret, _is_excluded


def test_germinate_writes_all_templates():
    d = tempfile.mkdtemp()
    try:
        rep = hatch(d, "fresh")
        root = rep["root"]
        for fn in ("BOOTSTRAP.md", "intent.md", "persona.md", "MOC.md", "example.md", "schedule.md"):
            assert os.path.exists(os.path.join(root, fn)), fn
        # intent defaults to ask
        import yaml
        fm = yaml.safe_load(open(os.path.join(root, "intent.md")).read().split("---")[1])
        assert fm["autonomy"] == "ask"
        assert os.path.isdir(os.path.join(root, ".obsidian"))
    finally:
        shutil.rmtree(d)


def test_incubate_adopts_tree_non_destructive():
    d = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(d, "sub"))
        with open(os.path.join(d, "a.md"), "w") as fh:
            fh.write("hello [[b]]\n")
        with open(os.path.join(d, "sub", "b.md"), "w") as fh:
            fh.write("world\n")
        rep = hatch(d, "adopt")
        assert "a.md" in rep["copied"]
        assert "sub/b.md" in rep["copied"]
        # original still present
        assert os.path.exists(os.path.join(d, "a.md"))
    finally:
        shutil.rmtree(d)


def test_incubate_excludes_secret_by_name():
    d = tempfile.mkdtemp()
    try:
        with open(os.path.join(d, "secrets.md"), "w") as fh:
            fh.write("do not ingest\n")
        # non-.md dotfiles are never scanned (safe by default), so just confirm
        with open(os.path.join(d, ".env"), "w") as fh:
            fh.write("API=1\n")
        with open(os.path.join(d, "real.md"), "w") as fh:
            fh.write("keep me\n")
        rep = hatch(d, "adopt")
        assert "secrets.md" in rep["excluded"]
        assert "real.md" in rep["copied"]
    finally:
        shutil.rmtree(d)


def test_incubate_excludes_secret_by_content():
    d = tempfile.mkdtemp()
    try:
        # benign filename, secret body
        with open(os.path.join(d, "notes.md"), "w") as fh:
            fh.write("my key is sk-abcdefghijklmnopqrstuvwxyz123456\n")
        with open(os.path.join(d, "ok.md"), "w") as fh:
            fh.write("normal note\n")
        rep = hatch(d, "adopt")
        assert any("notes.md" in e for e in rep["excluded"])
        assert "ok.md" in rep["copied"]
    finally:
        shutil.rmtree(d)


def test_hatch_refuses_home():
    home = os.path.expanduser("~")
    try:
        hatch(home, "fresh")
        assert False, "expected HatchError"
    except HatchError:
        pass


def test_hatch_allows_explicit_subdir_under_home():
    root = tempfile.mkdtemp(dir=os.path.expanduser("~"), prefix="sigil-home-subdir-")
    target = os.path.join(root, "brain")
    try:
        rep = hatch(target, "fresh")
        assert rep["root"] == os.path.realpath(target)
        assert os.path.exists(os.path.join(target, "BOOTSTRAP.md"))
    finally:
        shutil.rmtree(root)


def test_looks_secret_heuristics():
    assert _looks_secret("key: sk-abcdefghijklmnopqrstuvwxyz12")
    assert _looks_secret("-----BEGIN RSA PRIVATE KEY-----")
    assert _looks_secret("AKIAIOSFODNN7EXAMPLE")
    assert not _looks_secret("the cat sat on the mat")


def test_is_excluded_names():
    assert _is_excluded(".obsidian")
    assert _is_excluded("node_modules")
    assert _is_excluded("my.secret.md")
    assert not _is_excluded("normal-note.md")

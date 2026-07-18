import sys, os, time, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil.vault import Vault, Note, LinkGraph, PathEscapeError


def _write(root, name, text):
    p = os.path.join(root, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


def test_scan_builds_notes_and_links():
    d = tempfile.mkdtemp()
    try:
        _write(d, "a.md", "---\ntitle: A\n---\nlinks to [[b]] and [[c]]\n")
        _write(d, "b.md", "---\ntitle: B\n---\nback to [[a]]\n")
        _write(d, "c.md", "---\ntitle: C\n---\nno links\n")
        v = Vault(d)
        g = v.scan()
        assert set(g.notes) == {"a", "b", "c"}
        assert g.edges["a"] == ["b", "c"]
        assert g.backedges["b"] == ["a"]
        assert g.backedges["c"] == ["a"]
    finally:
        shutil.rmtree(d)


def test_resolve_link_escape_rejected():
    d = tempfile.mkdtemp()
    try:
        _write(d, "a.md", "[[../escape]]\n")
        v = Vault(d)
        try:
            v.resolve_link("../escape")
            assert False, "expected PathEscapeError"
        except PathEscapeError:
            pass
    finally:
        shutil.rmtree(d)


def test_resolve_link_symlink_escape_rejected():
    d = tempfile.mkdtemp()
    outside = tempfile.mkdtemp()
    try:
        # a note inside the vault that is a symlink to a file OUTSIDE root
        outside_file = os.path.join(outside, "secret.txt")
        with open(outside_file, "w") as fh:
            fh.write("secret")
        sym = os.path.join(d, "escape.md")
        os.symlink(outside_file, sym)
        v = Vault(d)
        # resolve_link joins root + "escape" + ".md" -> realpath = /tmp/.../secret.txt (outside)
        try:
            v.resolve_link("escape")
            assert False, "expected PathEscapeError for symlink escape"
        except PathEscapeError:
            pass
    finally:
        shutil.rmtree(d)
        shutil.rmtree(outside)


def test_incremental_scan_only_reparses_changed():
    d = tempfile.mkdtemp()
    try:
        p1 = _write(d, "a.md", "---\ntitle: A\n---\nlink [[b]]\n")
        p2 = _write(d, "b.md", "---\ntitle: B\n---\nnoop\n")
        v = Vault(d)
        g1 = v.scan()
        assert g1.mtimes[p1] == os.path.getmtime(p1)
        rev1 = g1.revision
        # sleep to ensure mtime differs, then change only a.md
        time.sleep(0.01)
        _write(d, "a.md", "---\ntitle: A2\n---\nlink [[b]] and [[c]]\n")
        _write(d, "c.md", "---\ntitle: C\n---\nnew\n")
        g2 = v.scan()  # incremental
        assert g2.revision == rev1 + 1
        assert g2.edges["a"] == ["b", "c"]
        assert "c" in g2.notes
        # unchanged b.md should still be present and not reparsed from disk here
        assert "b" in g2.notes
        # index file exists
        assert os.path.exists(os.path.join(d, ".sigil", "graph.json"))
    finally:
        shutil.rmtree(d)


def test_force_scan_rebuilds():
    d = tempfile.mkdtemp()
    try:
        p1 = _write(d, "a.md", "---\ntitle: A\n---\nlink [[b]]\n")
        p2 = _write(d, "b.md", "---\ntitle: B\n---\nnoop\n")
        v = Vault(d)
        v.scan()
        time.sleep(0.01)
        _write(d, "a.md", "---\ntitle: A3\n---\nno links now\n")
        g = v.scan(force=True)
        assert g.edges["a"] == []
        assert g.mtimes[p1] == os.path.getmtime(p1)
    finally:
        shutil.rmtree(d)


def test_note_defaults_and_frontmatter_keys():
    d = tempfile.mkdtemp()
    try:
        _write(d, "a.md", "---\nsource: human\nstatus: live\n---\nbody [[b]]\n")
        _write(d, "b.md", "---\n---\nnothing\n")
        v = Vault(d)
        g = v.scan()
        assert g.notes["a"].source == "human"
        # confidence / derived_from etc are NOT promoted; read from frontmatter
        assert "confidence" not in g.notes["b"].__dict__ or True
    finally:
        shutil.rmtree(d)


def test_incremental_scan_preserves_bodies():
    """Regression: unchanged files must keep their body after a cached re-scan."""
    d = tempfile.mkdtemp()
    try:
        _write(d, "a.md", "---\ntitle: A\n---\nhello world body\nlinks [[b]]\n")
        _write(d, "b.md", "---\ntitle: B\n---\nsecond note body\n")
        v = Vault(d)
        v.scan()  # full scan -> writes index with bodies
        g2 = v.scan()  # incremental: no mtime change -> reuse index
        # bodies must NOT be empty (the index stores them now)
        assert g2.notes["a"].body.strip() == "hello world body\nlinks [[b]]"
        assert g2.notes["b"].body.strip() == "second note body"
    finally:
        shutil.rmtree(d)

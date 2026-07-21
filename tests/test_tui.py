import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil import tui as T


def test_banner_exists():
    assert isinstance(T.banner(), str)
    assert "SIGIL" in T.banner() or "___" in T.banner()


def test_banner_mentions_sigil_wordmark():
    b = T.banner()
    assert "vault-native agent" in b
    assert "Setri" not in b
    assert "sigil" in b.lower()
    assert not b.startswith("\n")


def test_palette_plain_when_not_tty(monkeypatch):
    # force non-tty
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    pal = T._pal()
    assert pal["v"] == ""  # no color codes when piped
    assert pal["reset"] == ""


def test_walk_table_empty():
    out = T.walk_table([])
    assert "no notes" in out


def test_walk_table_rows():
    rows = [{"stem": "a", "score": 0.9, "hop": 0, "source": "human", "via": "root", "parent": "-"},
            {"stem": "b", "score": 0.4, "hop": 1, "source": "agent", "via": "backlink", "parent": "a"}]
    out = T.walk_table(rows)
    assert "a" in out and "b" in out and "human" in out
    assert "via" in out and "parent" in out
    assert "backlink" in out


def test_spinner_non_tty_no_crash(capsys, monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    with T.Spinner("doing thing"):
        pass
    captured = capsys.readouterr()
    assert "doing thing" in captured.out

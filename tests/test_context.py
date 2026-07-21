import sys, os, time, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil.vault import Vault
from sigil.provider import NullProvider
from sigil.context import ContextAssembler, ScoredNote

DAY = 86400.0


def _write(root, name, text):
    with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
        fh.write(text)


def _build():
    d = tempfile.mkdtemp()
    now = time.time()
    # a (active) links b, d and c; c is tombstoned; d has task tag
    _write(d, "a.md", f"---\ncreated: {now}\nhalf_life: 90\n---\nlink [[b]] [[d]] [[c]]\n")
    _write(d, "b.md", f"---\ncreated: {now}\nhalf_life: 90\n---\nb body\n")
    _write(d, "c.md", f"---\ncreated: {now}\nhalf_life: 90\nstatus: dead\n---\nc dead\n")
    _write(d, "d.md", f"---\ncreated: {now}\nhalf_life: 90\ntask: research\n---\nd task note\n")
    v = Vault(d)
    v.scan()
    return d, v


def test_exact_decay_at_half_life():
    # age == half_life => decay == 0.5 exactly
    assert ContextAssembler.decay_factor(10.0, 10.0) == 0.5
    # monotonic decreasing
    assert ContextAssembler.decay_factor(5.0, 10.0) > ContextAssembler.decay_factor(20.0, 10.0)
    assert ContextAssembler.decay_factor(0.0, 10.0) == 1.0


def test_tombstone_excluded_unless_requested():
    d, v = _build()
    try:
        ca = ContextAssembler(v, NullProvider())
        res = ca.assemble("a", request_dead=False)
        stems = [r.stem for r in res]
        assert "c" not in stems
        res2 = ca.assemble("a", request_dead=True)
        assert "c" in [r.stem for r in res2]
    finally:
        shutil.rmtree(d)


def test_zero_link_fallback_recency():
    d = tempfile.mkdtemp()
    try:
        now = time.time()
        _write(d, "lonely.md", f"---\ncreated: {now}\n---\nno links here\n")
        _write(d, "other.md", f"---\ncreated: {now - 10*DAY}\n---\nold\n")
        v = Vault(d)
        v.scan()
        ca = ContextAssembler(v, NullProvider())
        res = ca.assemble("lonely")
        # should still return notes (recency fallback), at least itself
        assert any(r.stem == "lonely" for r in res)
    finally:
        shutil.rmtree(d)


def test_tagmatch_ranks_higher():
    d, v = _build()
    try:
        ca = ContextAssembler(v, NullProvider())
        res = ca.assemble("a", task_tag="research")
        stems = [r.stem for r in res]
        # d (task: research) should be present and score above a non-matching peer
        d_score = next(r.score for r in res if r.stem == "d")
        # find a non-matching note that is reachable (b)
        b_score = next((r.score for r in res if r.stem == "b"), None)
        assert b_score is None or d_score > b_score
    finally:
        shutil.rmtree(d)


def test_tiebreak_created_desc():
    d = tempfile.mkdtemp()
    try:
        now = time.time()
        _write(d, "act.md", f"---\ncreated: {now}\n---\nactive [[x]] [[y]]\n")
        _write(d, "x.md", f"---\ncreated: {now}\nhalf_life: 90\n---\nx\n")
        _write(d, "y.md", f"---\ncreated: {now - 5*DAY}\nhalf_life: 90\n---\ny\n")
        v = Vault(d)
        v.scan()
        ca = ContextAssembler(v, NullProvider())
        res = ca.assemble("act")
        stems = [r.stem for r in res]
        # x and y have same structure; x created later -> should rank above y
        if "x" in stems and "y" in stems:
            assert stems.index("x") < stems.index("y")
    finally:
        shutil.rmtree(d)


def test_cache_hit_and_invalidation():
    d, v = _build()
    try:
        cache = {}
        ca = ContextAssembler(v, NullProvider(), cache=cache)
        r1 = ca.assemble("a")
        # second call on unchanged vault => cache hit (same list object)
        r2 = ca.assemble("a")
        assert r1 is r2
        # new linked note from a should appear after rescan
        _write(d, "e.md", f"---\ncreated: {time.time()}\n---\nlink [[a]]\n")
        v.scan()  # incremental, revision bumps
        r3 = ca.assemble("a")
        assert r3 is not r1
        assert "e" in [x.stem for x in r3]
    finally:
        shutil.rmtree(d)


def test_token_cap_trims():
    d = tempfile.mkdtemp()
    try:
        now = time.time()
        big = "word " * 5000  # ~20k chars => ~5k tokens
        _write(d, "act.md", f"---\ncreated: {now}\n---\nactive [[big]]\n")
        _write(d, "big.md", f"---\ncreated: {now}\nhalf_life: 90\n---\n{big}\n")
        v = Vault(d)
        v.scan()
        # small token budget
        class TinyProvider(NullProvider):
            max_context_tokens = 200
        ca = ContextAssembler(v, TinyProvider())
        res = ca.assemble("act")
        total = sum(max(1, len(r.body)//4) for r in res)
        assert total <= 200 + 50  # within budget (+slack for first pick)
    finally:
        shutil.rmtree(d)


def test_provenance_tracks_forward_and_backlink_parent():
    d = tempfile.mkdtemp()
    try:
        now = time.time()
        _write(d, "boot.md", f"---\ncreated: {now}\n---\nforward [[moc]]\n")
        _write(d, "moc.md", f"---\ncreated: {now}\n---\nlinks [[boot]] [[child]]\n")
        _write(d, "child.md", f"---\ncreated: {now}\n---\nchild body\n")
        _write(d, "back.md", f"---\ncreated: {now}\n---\npoints back [[boot]]\n")
        v = Vault(d)
        v.scan()
        ca = ContextAssembler(v, NullProvider())
        res = ca.assemble("boot")
        by_stem = {r.stem: r for r in res}
        assert by_stem["boot"].via == "root"
        assert by_stem["boot"].parent is None
        assert by_stem["moc"].via == "forward"
        assert by_stem["moc"].parent == "boot"
        assert by_stem["back"].via == "backlink"
        assert by_stem["back"].parent == "boot"
    finally:
        shutil.rmtree(d)

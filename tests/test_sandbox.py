import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil import sandbox as S
from sigil import autonomy as auto
from sigil import hatch as hatchmod
from sigil import lock


def _hatch():
    d = tempfile.mkdtemp()
    hatchmod.hatch(d, "fresh")
    return d


def test_sandbox_confines_to_delegates_dir():
    d = _hatch()
    try:
        sb = S.Sandbox(d)
        ok = os.path.join(d, "delegates", "child.md")
        bad = os.path.join(d, "notes", "escape.md")
        assert sb.confined(ok) is True
        assert sb.confined(bad) is False
        # escape via .. must be rejected
        escape = os.path.join(d, "delegates", "..", "evil.md")
        assert sb.confined(escape) is False
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_sandbox_spawn_writes_gated_note():
    d = _hatch()
    try:
        intent = auto.load_intent(d)
        gate = auto.gate_from_intent(intent)
        sb = S.Sandbox(d)
        path = sb.spawn("scout", "explore the repo", gate=None)
        assert path.endswith("delegates/scout.md")
        assert os.path.exists(path)
        assert "scout.md" in sb.list_delegates()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_delegate_tier_downgraded_without_sandbox():
    intent = {"autonomy": "delegate", "allowed": ["delegate"]}
    # no sandbox -> downgrade to ask
    assert auto.resolve_tier(intent, 0.9, sandbox_active=False) == "ask"
    # sandbox active + allowed -> delegate
    assert auto.resolve_tier(intent, 0.9, sandbox_active=True) == "delegate"
    # low confidence -> ask regardless
    assert auto.resolve_tier(intent, 0.3, sandbox_active=True) == "ask"


def test_request_delegate_refused_without_intent_allow():
    d = _hatch()
    try:
        # build an intent that allows some writes but NOT delegate
        intent_path = os.path.join(d, "intent.md")
        txt = open(intent_path, encoding="utf-8").read()
        txt = txt.replace("  - \"*\"\n", "  - \"write\"\n")
        open(intent_path, "w", encoding="utf-8").write(txt)
        intent = auto.load_intent(d)
        assert "delegate" not in intent.get("allowed", [])
        res = auto.request_delegate(d, "x", "brief", intent)
        assert res["ok"] is False
        assert "delegate" in res["reason"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_request_delegate_spawns_when_allowed():
    d = _hatch()
    try:
        # opt in explicitly: write an intent that allows delegate
        intent_path = os.path.join(d, "intent.md")
        open(intent_path, "w", encoding="utf-8").write(
            "---\ntitle: intent\nstatus: live\nsource: human\nautonomy: delegate\n"
            "allowed:\n  - \"*\"\n  - \"delegate\"\nforbidden: []\n---\n"
        )
        intent = auto.load_intent(d)
        assert "delegate" in intent.get("allowed", [])
        res = auto.request_delegate(d, "worker", "do a task", intent)
        assert res["ok"] is True
        assert os.path.exists(res["path"])
        assert "delegates/worker.md" in res["path"]
    finally:
        shutil.rmtree(d, ignore_errors=True)

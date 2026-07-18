import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil import autonomy as A
from sigil.frontmatter import parse, emit
from sigil.lock import IntentGate

import yaml


def _write(root, name, text):
    with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
        fh.write(text)


def _writepath(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def test_load_intent_defaults_when_missing():
    d = tempfile.mkdtemp()
    try:
        intent = A.load_intent(d)
        assert intent["autonomy"] == "ask"
        assert intent["allowed"] == ["*"]
    finally:
        shutil.rmtree(d)


def test_intent_reloaded_every_call_not_cached():
    d = tempfile.mkdtemp()
    try:
        _write(d, "intent.md", "---\nautonomy: act\nstatus: live\n---\n# intent\n")
        i1 = A.load_intent(d)
        # edit on disk
        _write(d, "intent.md", "---\nautonomy: ask\nstatus: live\n---\n# intent\n")
        i2 = A.load_intent(d)
        assert i1["autonomy"] == "act"
        assert i2["autonomy"] == "ask"  # re-read reflects change
    finally:
        shutil.rmtree(d)


def test_resolve_tier_low_confidence_forces_ask():
    d = tempfile.mkdtemp()
    try:
        _write(d, "intent.md", "---\nautonomy: act\n---\n# i\n")
        intent = A.load_intent(d)
        assert A.resolve_tier(intent, 0.9) == "act"
        assert A.resolve_tier(intent, 0.3) == "ask"  # forced
        assert A.resolve_tier(intent, None) == "act"
    finally:
        shutil.rmtree(d)


def test_halt_via_killswitch_file():
    d = tempfile.mkdtemp()
    try:
        assert A.is_halted(d) is False
        A.halt(d, "manual stop")
        assert A.is_halted(d) is True
        # file present + status halt
        assert os.path.exists(os.path.join(d, "KILLSWITCH.md"))
    finally:
        shutil.rmtree(d)


def test_halt_via_intent_status():
    d = tempfile.mkdtemp()
    try:
        _write(d, "intent.md", "---\nautonomy: act\nstatus: halt\n---\n# i\n")
        assert A.is_halted(d) is True
    finally:
        shutil.rmtree(d)


def test_halt_via_tombstoned_root():
    d = tempfile.mkdtemp()
    try:
        _write(d, "BOOTSTRAP.md", "---\nstatus: dead\n---\n# root\n")
        assert A.is_halted(d) is True
    finally:
        shutil.rmtree(d)


def test_proposal_requires_human_approval():
    d = tempfile.mkdtemp()
    try:
        gate = IntentGate(allowed=["*"], forbidden=[])
        path = A.write_proposal(d, "do-thing", "write note X", gate)
        # not approved yet
        can, st = A.poll_proposal(d, "do-thing")
        assert can is False
        assert st[0] == "pending"
        # agent self-approves (source: agent) -> must NOT count
        _writepath(path, "---\nstatus: approved\nsource: agent\n---\n# p\n")
        can, st = A.poll_proposal(d, "do-thing")
        assert can is False
        # human approves
        _writepath(path, "---\nstatus: approved\nsource: human\n---\n# p\n")
        can, st = A.poll_proposal(d, "do-thing")
        assert can is True
    finally:
        shutil.rmtree(d)


def test_proposal_content_hash_changes_on_edit():
    d = tempfile.mkdtemp()
    try:
        gate = IntentGate(allowed=["*"], forbidden=[])
        A.write_proposal(d, "x", "do x", gate)
        _, st1 = A.poll_proposal(d, "x")
        h1 = st1[2]
        # human approves
        p = os.path.join(d, "_proposal_x.md")
        _writepath(p, "---\nstatus: approved\nsource: human\n---\n# p\n")
        can, st2 = A.poll_proposal(d, "x")
        assert can is True
        assert st2[2] != h1  # hash changed when content edited
    finally:
        shutil.rmtree(d)


def test_heartbeat_once_creates_due_note():
    d = tempfile.mkdtemp()
    try:
        sched = "# schedule\n0 9 * * * | daily-review\n"
        results = A.heartbeat_once(d, sched)
        assert len(results) == 1
        assert results[0]["target"] == "daily-review"
        assert results[0]["result"] in ("created", "touched")
        assert os.path.exists(os.path.join(d, "daily-review.md"))
    finally:
        shutil.rmtree(d)

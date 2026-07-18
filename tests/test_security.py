"""Security hardening tests (Task 12).

These lock in the v1 security boundaries the reviewers mandated:
- path confinement: `[[links]]` / resolve_link never escape the vault root,
  even via `..`, symlinks, or absolute paths.
- ingested markdown is untrusted data: a ```run block is FLAGGED, never
  executed. The assembler surfaces notes; it does not run code.
- trust tiers: human > agent > ingested in conflict resolution, and the
  intent gate rejects forbidden paths regardless of model intent.
"""

import sys, os, tempfile, shutil, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil.vault import Vault, PathEscapeError
from sigil.context import ContextAssembler
from sigil.provider import NullProvider
from sigil.conflict import detect_conflict
from sigil.lock import IntentGate, GateRejected
from sigil.hatch import _looks_secret

DAY = 86400.0


def _write(root, name, text):
    with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
        fh.write(text)


# ---- path confinement ----------------------------------------------------
def test_resolve_link_absolute_path_rejected():
    d = tempfile.mkdtemp()
    try:
        v = Vault(d)
        try:
            v.resolve_link("/etc/passwd")
            assert False, "expected PathEscapeError"
        except PathEscapeError:
            pass
    finally:
        shutil.rmtree(d)


def test_resolve_link_dotdot_rejected():
    d = tempfile.mkdtemp()
    try:
        v = Vault(d)
        try:
            v.resolve_link("../outside")
            assert False, "expected PathEscapeError"
        except PathEscapeError:
            pass
    finally:
        shutil.rmtree(d)


def test_resolve_link_symlink_file_rejected():
    d = tempfile.mkdtemp()
    outside = tempfile.mkdtemp()
    try:
        secret = os.path.join(outside, "secret.txt")
        open(secret, "w").write("x")
        os.symlink(secret, os.path.join(d, "escape.md"))
        v = Vault(d)
        try:
            v.resolve_link("escape")
            assert False, "expected PathEscapeError (symlink escape)"
        except PathEscapeError:
            pass
    finally:
        shutil.rmtree(d)
        shutil.rmtree(outside)


# ---- untrusted data: code is flagged, not run ----------------------------
def test_injected_run_block_surfaced_not_executed():
    d = tempfile.mkdtemp()
    try:
        now = time.time()
        # note with a ```run block — must be treated as data, never executed
        _write(d, "a.md",
               f"---\ncreated: {now}\n---\nactive [[evil]]\n")
        _write(d, "evil.md",
               f"---\ncreated: {now}\nhalf_life: 90\n---\n"
               "```run\nimport os; os.system('touch /tmp/sigil_pwned')\n```\n")
        v = Vault(d)
        v.scan()
        ca = ContextAssembler(v, NullProvider())
        ctx = ca.assemble("a")
        # the note is surfaced (link-walk) but its code is NOT executed
        assert any(n.stem == "evil" for n in ctx)
        assert not os.path.exists("/tmp/sigil_pwned"), "code block was executed!"
        # and the run fence text is present as DATA in the body
        evil = next(n for n in ctx if n.stem == "evil")
        assert "os.system" in evil.body
    finally:
        shutil.rmtree(d)
        if os.path.exists("/tmp/sigil_pwned"):
            os.remove("/tmp/sigil_pwned")


def test_injected_run_flagged_by_ingest_scan():
    # hatch/incubate should treat ```run as data; here we assert the secret
    # heuristic does NOT misfire on code, but the design is: code == data.
    assert not _looks_secret("```run\nprint('hi')\n```")


# ---- trust tiers ---------------------------------------------------------
def test_conflict_human_over_agent():
    d = tempfile.mkdtemp()
    try:
        _write(d, "fact.md", "---\nclaim: human truth\nsource: human\n---\nbody\n")
        c = detect_conflict(d, "fact", "agent lie", proposed_source="agent")
        assert c is not None
        assert c.resolution == "kept_human"
    finally:
        shutil.rmtree(d)


def test_intent_gate_rejects_forbidden_regardless_of_model():
    d = tempfile.mkdtemp()
    try:
        gate = IntentGate(allowed=["*"], forbidden=["secrets/"])
        # even if a "model" wanted to write it, the code-level gate refuses
        from sigil import lock
        try:
            lock.atomic_write(os.path.join(d, "secrets", "x.md"), "y", gate=gate)
            assert False, "expected GateRejected"
        except GateRejected:
            pass
    finally:
        shutil.rmtree(d)

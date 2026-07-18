"""End-to-end test on a /tmp copy (Task 13).

We build a realistic linked markdown tree in /tmp (NEVER ~/), adopt it via
hatch (proving the secret filter + loose INCUBATE), then exercise the full
pipeline: scan -> link-walk -> chat (NullProvider) -> conflict -> proposal
-> halt. This is the integration proof that all 12 tasks compose.

The tree mimics a personal-agent vault: AGENTS, SOUL, USER, MEMORY notes
with [[wikilinks]], a tombstoned note, and a secrets.md that must be excluded.
"""

import sys, os, tempfile, shutil, subprocess, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil import hatch as hatchmod
from sigil.vault import Vault
from sigil.context import ContextAssembler
from sigil.provider import NullProvider
from sigil.conflict import detect_conflict, record_conflict
from sigil import autonomy as auto
from sigil.persona import load_persona
from sigil import lock

REAL_TREE = {
    "AGENTS.md": "---\nsource: human\n---\n# AGENTS\nRead SOUL.md and USER.md. See [[MEMORY]].\n",
    "SOUL.md": "---\nsource: human\n---\n# SOUL\nI am a direct agent. Link [[USER]].\n",
    "USER.md": "---\nsource: human\n---\n# USER\nArch Linux dev. See [[SOUL]] and [[AGENTS]].\n",
    "MEMORY.md": "---\nsource: human\nhalf_life: 90\n---\n# MEMORY\nNotes link [[SOUL]] and [[USER]].\n",
    "old_idea.md": "---\nsource: agent\nhalf_life: 10\nstatus: dead\n---\n# old\nforgotten idea, tombstoned.\n",
    "secrets.md": "---\nsource: human\n---\nsk-abcdefghijklmnopqrstuvwxyz1234567890\n",
    "project.md": "---\nsource: human\nclaim: sigil is a vault agent\ntask: build\n---\n# project\nBuilding [[MEMORY]].\n",
}


def _build_tree():
    d = tempfile.mkdtemp()
    for name, text in REAL_TREE.items():
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    return d


def test_e2e_adopt_scan_walk():
    d = _build_tree()
    try:
        rep = hatchmod.hatch(d, "adopt")
        # secret excluded
        assert "secrets.md" in rep["excluded"]
        assert any("secret" in e for e in rep["excluded"])
        # real notes copied
        assert "AGENTS.md" in [n if n.endswith(".md") else n for n in rep["copied"]]
        vault = Vault(d)
        g = vault.scan()
        # link graph built
        assert "AGENTS" in g.notes
        assert "SOUL" in g.backedges  # AGENTS links SOUL
        # link-walk from MEMORY surfaces linked notes
        ca = ContextAssembler(vault, NullProvider())
        ctx = ca.assemble("MEMORY")
        stems = [n.stem for n in ctx]
        assert "SOUL" in stems
        assert "USER" in stems
        # tombstoned excluded by default
        assert "old_idea" not in stems
    finally:
        shutil.rmtree(d)


def test_e2e_chat_with_null_provider():
    d = _build_tree()
    try:
        hatchmod.hatch(d, "adopt")
        vault = Vault(d)
        vault.scan()
        persona = load_persona(d)  # hatch ensures persona.md exists for adopted vaults
        assert persona.source == "persona.md"
        ca = ContextAssembler(vault, NullProvider())
        ctx = ca.assemble("AGENTS")
        joined = persona.system_prompt() + "\n" + "\n".join(n.body for n in ctx)
        out = NullProvider().complete(joined)
        assert "null-provider-echo" in out
    finally:
        shutil.rmtree(d)


def test_e2e_conflict_logged():
    d = _build_tree()
    try:
        hatchmod.hatch(d, "adopt")
        # project.md has claim: sigil is a vault agent (source agent)
        # human asserts a conflicting claim
        c = detect_conflict(d, "project", "sigil is a RAG bot", proposed_source="human")
        assert c is not None
        assert c.resolution == "kept_human"
        log = record_conflict(d, c)
        assert os.path.exists(log)
    finally:
        shutil.rmtree(d)


def test_e2e_proposal_and_halt():
    d = _build_tree()
    try:
        hatchmod.hatch(d, "adopt")
        gate = lock.IntentGate(allowed=["*"], forbidden=[])
        # agent writes a proposal (does NOT act yet)
        p = auto.write_proposal(d, "write-note", "create summary.md", gate)
        can, _ = auto.poll_proposal(d, "write-note")
        assert can is False  # not yet approved
        # human approves
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("---\nstatus: approved\nsource: human\n---\n# proposal\n")
        can, _ = auto.poll_proposal(d, "write-note")
        assert can is True
        # halt works
        assert auto.is_halted(d) is False
        auto.halt(d, "test")
        assert auto.is_halted(d) is True
    finally:
        shutil.rmtree(d)


def test_e2e_never_walks_home():
    # the adopt target must refuse ~; here we assert hatch refuses home
    try:
        hatchmod.hatch(os.path.expanduser("~"), "fresh")
        assert False, "hatch should refuse home"
    except hatchmod.HatchError:
        pass

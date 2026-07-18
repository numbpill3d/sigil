import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil.provenance import stamp
from sigil.lock import IntentGate

import yaml


def test_stamp_writes_provenance_block():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "note.md")
        stamp(p, "body text", source="agent", derived_from=["a", "b"], model="null", confidence=0.8)
        text = open(p, encoding="utf-8").read()
        fm = yaml.safe_load(text.split("---")[1])
        assert fm["provenance"]["source"] == "agent"
        assert fm["provenance"]["derived_from"] == ["a", "b"]
        assert fm["provenance"]["model"] == "null"
        assert fm["provenance"]["confidence"] == 0.8
        assert "body text" in text
    finally:
        shutil.rmtree(d)


def test_stamp_preserves_existing_body():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "n.md")
        stamp(p, "original body", source="human", derived_from=[])
        stamp(p, "new body", source="agent", derived_from=["x"], preserve_body=True)
        text = open(p, encoding="utf-8").read()
        assert "original body" in text
        # provenance updated
        fm = yaml.safe_load(text.split("---")[1])
        assert fm["provenance"]["derived_from"] == ["x"]
    finally:
        shutil.rmtree(d)


def test_stamp_respects_gate():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "secret.md")
        gate = IntentGate(allowed=["*"], forbidden=["secret"])
        try:
            stamp(p, "x", gate=gate)
            assert False, "expected GateRejected"
        except Exception:
            pass
    finally:
        shutil.rmtree(d)

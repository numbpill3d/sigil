import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil import hatch as hatchmod
from sigil.vault import Vault
from sigil import persona as P


def _hatch():
    d = tempfile.mkdtemp()
    hatchmod.hatch(d, "fresh")
    return d


def _write_persona(d, voice, tone, rules):
    import yaml
    fm = {"voice": voice, "tone": tone, "rules": rules}
    body = yaml.safe_dump(fm) + "\n# Persona\n"
    # wrap in frontmatter fences
    text = "---\n" + body + "---\n# Persona\n"
    with open(os.path.join(d, "persona.md"), "w", encoding="utf-8") as fh:
        fh.write(text)


def test_first_scan_records_baseline_no_drift():
    d = _hatch()
    try:
        v = Vault(d)
        res = v.scan()  # triggers _check_drift
        # baseline recorded, no drift note
        assert not os.path.exists(os.path.join(d, "_persona_drift.md"))
        snap = os.path.join(d, ".sigil", "persona.snapshot.json")
        assert os.path.exists(snap)
    finally:
        shutil.rmtree(d)


def test_persona_edit_detected_and_logged():
    d = _hatch()
    try:
        v = Vault(d)
        v.scan()  # baseline
        # edit persona voice
        _write_persona(d, "loud uppercase", "angry", ["never invent data"])
        res = P.check_drift(d)
        assert res["changed"] is True
        assert "voice" in res["fields"]
        assert os.path.exists(os.path.join(d, "_persona_drift.md"))
        text = open(os.path.join(d, "_persona_drift.md"), encoding="utf-8").read()
        assert "loud uppercase" in text
        assert "voice" in text
    finally:
        shutil.rmtree(d)


def test_no_drift_on_identical_rescan():
    d = _hatch()
    try:
        v = Vault(d)
        v.scan()
        # rescan with no change -> no drift
        res = P.check_drift(d)
        assert res["changed"] is False
        assert not os.path.exists(os.path.join(d, "_persona_drift.md"))
    finally:
        shutil.rmtree(d)


def test_drift_field_listed_correctly():
    d = _hatch()
    try:
        v = Vault(d)
        v.scan()
        _write_persona(d, "lowercase dry", "witty", ["rule a", "rule b", "rule c"])
        res = P.check_drift(d)
        # tone + rules changed (voice unchanged from template default "lowercase dry")
        assert res["changed"] is True
        assert "tone" in res["fields"]
        assert "rules" in res["fields"]
    finally:
        shutil.rmtree(d)


def test_drift_note_routes_through_lock():
    # provenance/lock path is exercised; just assert drift note is valid md
    d = _hatch()
    try:
        v = Vault(d)
        v.scan()
        _write_persona(d, "changed", "changed", ["x"])
        v.scan()
        p = os.path.join(d, "_persona_drift.md")
        assert os.path.exists(p)
        # frontmatter parses
        from sigil.frontmatter import parse
        fm, body = parse(open(p, encoding="utf-8").read())
        assert fm["title"] == "persona-drift"
    finally:
        shutil.rmtree(d)

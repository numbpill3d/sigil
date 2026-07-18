import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil.persona import load_persona, Persona, drift_detect, DEFAULT_PERSONA


def _write(root, name, text):
    with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
        fh.write(text)


def test_default_when_missing():
    d = tempfile.mkdtemp()
    try:
        p = load_persona(d)
        assert p.source == "default"
        assert "direct" in p.voice
    finally:
        shutil.rmtree(d)


def test_loads_persona_md():
    d = tempfile.mkdtemp()
    try:
        _write(d, "persona.md",
               "---\nvoice: lowercase dry\n"
               "tone: witty\nrules:\n  - never invent data\n  - be honest\n---\n# Persona\n")
        p = load_persona(d)
        assert p.source == "persona.md"
        assert p.voice == "lowercase dry"
        assert p.tone == "witty"
        assert len(p.rules) == 2
    finally:
        shutil.rmtree(d)


def test_system_prompt_contains_fields():
    d = tempfile.mkdtemp()
    try:
        _write(d, "persona.md",
               "---\nvoice: v\n"
               "tone: t\nrules:\n  - r1\n  - r2\n---\nbody\n")
        p = load_persona(d)
        sp = p.system_prompt()
        assert "v" in sp and "t" in sp and "r1" in sp and "r2" in sp
    finally:
        shutil.rmtree(d)


def test_drift_detect():
    a = {"voice": "x", "tone": "y"}
    b = {"voice": "x", "tone": "z"}
    assert drift_detect(a, b) == ["tone"]

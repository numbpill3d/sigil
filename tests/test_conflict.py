import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil.conflict import detect_conflict, record_conflict, Conflict

import yaml


def _write(root, name, text):
    with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
        fh.write(text)


def test_human_claim_wins_default():
    d = tempfile.mkdtemp()
    try:
        _write(d, "fact.md", "---\nclaim: earth is flat\nsource: human\n---\nbody\n")
        c = detect_conflict(d, "fact", "earth is round", proposed_source="agent")
        assert c is not None
        assert c.resolution == "kept_human"
    finally:
        shutil.rmtree(d)


def test_agent_over_ingested():
    d = tempfile.mkdtemp()
    try:
        _write(d, "fact.md", "---\nclaim: x is 1\nsource: ingested\n---\nbody\n")
        c = detect_conflict(d, "fact", "x is 2", proposed_source="agent")
        assert c is not None
        assert c.resolution == "agent_over_ingested"
    finally:
        shutil.rmtree(d)


def test_no_conflict_when_same():
    d = tempfile.mkdtemp()
    try:
        _write(d, "fact.md", "---\nclaim: same\nsource: human\n---\nbody\n")
        c = detect_conflict(d, "fact", "same", proposed_source="agent")
        assert c is None
    finally:
        shutil.rmtree(d)


def test_record_conflict_writes_log():
    d = tempfile.mkdtemp()
    try:
        _write(d, "fact.md", "---\nclaim: a\nsource: human\n---\nbody\n")
        c = detect_conflict(d, "fact", "b", proposed_source="agent")
        log = record_conflict(d, c)
        assert os.path.exists(log)
        text = open(log, encoding="utf-8").read()
        assert "kept_human" in text
        assert "fact" in text
    finally:
        shutil.rmtree(d)

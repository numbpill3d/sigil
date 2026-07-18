import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil.frontmatter import parse, emit, split, roundtrip, FrontmatterError


def test_parse_scalar_and_types():
    text = "---\nkey: val\nnum: 3\nflag: true\nratio: 0.5\n---\nbody text\n"
    fm, body = parse(text)
    assert fm["key"] == "val"
    assert fm["num"] == 3
    assert fm["flag"] is True
    assert fm["ratio"] == 0.5
    assert body == "body text\n"


def test_parse_quoted_string_with_colon():
    text = '---\ntitle: "error: thing happened"\n---\nbody\n'
    fm, _ = parse(text)
    assert fm["title"] == "error: thing happened"


def test_parse_inline_list():
    text = "---\ntags: [a, b, c]\n---\nbody\n"
    fm, _ = parse(text)
    assert fm["tags"] == ["a", "b", "c"]


def test_parse_nested_map():
    text = "---\nclaim:\n  topic: x\n  value: true\n---\nbody\n"
    fm, _ = parse(text)
    assert fm["claim"] == {"topic": "x", "value": True}


def test_no_frontmatter_returns_empty():
    text = "just body\n"
    fm, body = parse(text)
    assert fm == {}
    assert body == "just body\n"


def test_empty_body_ok():
    text = "---\nkey: val\n---\n"
    fm, body = parse(text)
    assert fm["key"] == "val"
    assert body == ""


def test_missing_closing_fence_raises():
    text = "---\nkey: val\nno closing\n"
    try:
        parse(text)
        assert False, "expected FrontmatterError"
    except FrontmatterError:
        pass


def test_no_trailing_newline_ok():
    text = "---\nkey: val\n---\nbody"  # no trailing newline
    fm, body = parse(text)
    assert fm["key"] == "val"
    assert body == "body"


def test_roundtrip_preserves_data():
    text = (
        '---\n'
        'title: "error: x"\n'
        "num: 3\n"
        "flag: true\n"
        "tags: [a, b]\n"
        "claim:\n"
        "  topic: x\n"
        "  value: true\n"
        "---\n"
        "body line one\nbody line two\n"
    )
    fm2, body2 = roundtrip(text)
    assert fm2["title"] == "error: x"
    assert fm2["num"] == 3
    assert fm2["flag"] is True
    assert fm2["tags"] == ["a", "b"]
    assert fm2["claim"] == {"topic": "x", "value": True}
    assert body2 == "body line one\nbody line two\n"


def test_emit_keeps_unknown_keys():
    fm = {"a": 1, "b": "two", "custom_key": "keep me"}
    out = emit(fm, "body\n")
    fm2, _ = parse(out)
    assert fm2["custom_key"] == "keep me"
    assert fm2["a"] == 1


def test_emit_no_frontmatter_returns_body():
    assert emit({}, "just body\n") == "just body\n"

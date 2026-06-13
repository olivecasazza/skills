#!/usr/bin/env python3
"""Deterministic eval for the vault-organize skill.

Runs sandboxed (no network): loads the skill's `vault-classify` tool and asserts
its pure-logic contract — frontmatter stripping, chat payload construction,
content truncation, and strict-JSON parse/normalize (category validation, fence
stripping, type coercion). The behavioral half (does the model classify well?)
is the Archon/Instructor workflow in behavioral.md, which needs the live
cliproxyapi backend.

Convention: every skill with deterministic guarantees gets evals/<skill>/test.py.
The flake auto-registers each as `checks.<system>.<skill>-eval`.
"""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "riglets" / "vault-organize" / "vault-classify.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("vault_classify", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    tool = load_tool()

    # 1. Frontmatter stripping: leading YAML block removed, body preserved.
    note = "---\ntitle: Foo\ntags: [a]\n---\n\n# Heading\n\nReal body here.\n"
    body = tool.strip_frontmatter(note)
    assert body == "# Heading\n\nReal body here.", f"frontmatter not stripped: {body!r}"
    # No frontmatter -> unchanged (modulo strip).
    assert tool.strip_frontmatter("just text") == "just text", "no-frontmatter mangled"

    # 2. Payload construction: model, temperature=0, single user message with
    #    the note content embedded; empty notes get a placeholder.
    payload = tool.build_payload("hello world", "gpt-5.5")
    assert payload["model"] == "gpt-5.5", "model not set"
    assert payload["temperature"] == 0, "temperature must be 0 for determinism"
    assert len(payload["messages"]) == 1 and payload["messages"][0]["role"] == "user"
    assert "hello world" in payload["messages"][0]["content"], "content not embedded"
    empty = tool.build_payload("   ", "m")
    assert "(empty note)" in empty["messages"][0]["content"], "empty note not handled"

    # 3. Content truncation at 8000 chars.
    big = tool.build_payload("x" * 9000, "m")["messages"][0]["content"]
    assert big.count("x") == 8000, "content not truncated to 8000 chars"

    # 4. Payload is JSON-serializable (valid request body).
    json.dumps(payload)

    # 5. parse_classification: a clean reply normalizes correctly.
    raw = json.dumps(
        {
            "category": "research",
            "tags": ["ml", "vault"],
            "entities": [{"name": "Neo4j", "type": "tool"}],
            "summary": "A note about ML.",
        }
    )
    v = tool.parse_classification(raw)
    assert v["category"] == "research", "valid category dropped"
    assert v["tags"] == ["ml", "vault"], "tags not preserved"
    assert v["entities"][0] == {"name": "Neo4j", "type": "tool"}, "entity not normalized"
    assert v["summary"] == "A note about ML.", "summary not preserved"

    # 6. Unknown category -> fallback 'reference'.
    bad = tool.parse_classification(json.dumps({"category": "nonsense"}))
    assert bad["category"] == "reference", "unknown category not defaulted"
    assert bad["tags"] == [] and bad["entities"] == [], "missing fields not defaulted"

    # 7. Code-fenced reply is tolerated.
    fenced = "```json\n" + json.dumps({"category": "docs"}) + "\n```"
    assert tool.parse_classification(fenced)["category"] == "docs", "fence not stripped"

    # 8. Summary clamped to 120 chars; malformed entities filtered out.
    clamp = tool.parse_classification(
        json.dumps({"category": "archive", "summary": "z" * 200, "entities": ["bad", {"name": "ok"}]})
    )
    assert len(clamp["summary"]) == 120, "summary not clamped"
    assert clamp["entities"] == [{"name": "ok", "type": "unknown"}], "bad entities not filtered"

    # 9. Non-object JSON reply is rejected.
    try:
        tool.parse_classification("[1, 2, 3]")
        raise AssertionError("non-object reply should raise")
    except ValueError:
        pass

    print("vault-organize eval: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        sys.exit(f"vault-organize eval FAILED: {e}")

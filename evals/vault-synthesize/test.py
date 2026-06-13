#!/usr/bin/env python3
"""Deterministic eval for the vault-synthesize skill.

Runs sandboxed (no network): loads the skill's `vault-synthesize` tool and
asserts the pure-logic contract that the agent relies on — slug determinism,
chat/completions payload shape, response parsing, and concept-note assembly
(member preservation + wiki-link fallback). This is the structural half; the
behavioral half (is the synthesis actually good?) is the Archon/Instructor
workflow in behavioral.md, which needs the live cliproxyapi backend.

Convention: ROOT = parents[2]; load_tool via importlib; assert; print PASS.
The flake auto-registers this as `checks.<system>.vault-synthesize-eval`.
"""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "riglets" / "vault-synthesize" / "vault-synthesize.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("vault_synthesize", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    tool = load_tool()

    members = [
        "projects/foo/setup.md",
        "cluster/seir/gpu.md",
        "reference/nix/flakes.md",
    ]

    # 1. Slug is deterministic and ORDER-INDEPENDENT (sorted-set keyed).
    s1 = tool.concept_slug(members)
    s2 = tool.concept_slug(list(reversed(members)))
    assert s1 == s2, "slug changed under member reordering"
    assert len(s1) == 8 and all(c in "0123456789abcdef" for c in s1), "slug not 8 hex chars"

    # 2. Payload shape: right model, system + user messages, divider-joined notes.
    snippets = ["### A\n\nalpha body", "### B\n\nbeta body"]
    payload = tool.build_payload(snippets, model="claude-sonnet-4-6")
    assert payload["model"] == "claude-sonnet-4-6", "model not threaded into payload"
    roles = [m["role"] for m in payload["messages"]]
    assert roles == ["system", "user"], f"unexpected message roles: {roles}"
    assert "\n\n---\n\n" in payload["messages"][1]["content"], "snippets not joined with divider"
    assert "alpha body" in payload["messages"][1]["content"], "snippet content missing"
    json.dumps(payload)  # must be a valid JSON request body

    # 3. Response parsing pulls choices[0].message.content (from a fixture dict).
    fixture = {"choices": [{"message": {"content": "  synthesized text  "}}]}
    assert tool.parse_response(fixture) == "synthesized text", "response parse/strip wrong"

    # 4. Concept assembly: frontmatter shape, members preserved, slug matches.
    body_no_links = "A summary with no wiki links at all."
    fm, body = tool.assemble_concept(members, body_no_links, "2026-06-13T00:00:00Z")
    assert fm["members"] == members, "members not preserved in order"
    assert fm["slug"] == s1, "frontmatter slug != concept_slug(members)"
    assert "concept" in fm["tags"] and "auto-generated" in fm["tags"], "concept tags missing"
    # Fallback: body had no links, so member links must be appended.
    assert "[[projects/foo/setup.md|setup]]" in body, "wiki-link fallback not appended"
    assert "## Members" in body, "members section not appended on fallback"

    # 5. If the LLM body already has links, we DON'T double-append.
    body_with_links = "Summary.\n\n## Members\n- [[x|x]]"
    _, body2 = tool.assemble_concept(members, body_with_links, "2026-06-13T00:00:00Z")
    assert body2 == body_with_links, "links clobbered/duplicated when already present"

    # 6. Rendered note round-trips: frontmatter values are JSON-encoded, body follows.
    note = tool.render_note(fm, body)
    assert note.startswith("---\n"), "note missing frontmatter open"
    assert f'slug: {json.dumps(s1)}' in note, "slug not JSON-encoded in frontmatter"
    assert note.rstrip().endswith(body.rstrip()), "body not appended after frontmatter"

    print("vault-synthesize eval: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        sys.exit(f"vault-synthesize eval FAILED: {e}")

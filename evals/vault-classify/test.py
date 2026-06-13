#!/usr/bin/env python3
"""Deterministic eval for the vault-classify skill.

Runs sandboxed (no network): loads the skill's `vault-classify` tool and asserts
its pure-logic contract — frontmatter parsing, /v1/chat/completions payload
construction, model-response normalization, and frontmatter stamping. This is
the structural half of the eval; the behavioral half (does the model pick the
RIGHT category?) is the Archon/Instructor workflow in behavioral.md, which needs
a live chat backend.

Convention: every skill with deterministic guarantees gets evals/<skill>/test.py.
The flake auto-registers each as `checks.<system>.<skill>-eval`.
"""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "riglets" / "vault-classify" / "vault-classify.py"

NOTE = """\
---
title: "Cilium L2 LB for game servers"
tags: ["networking", "k8s"]
ingested_at: "2026-06-01T00:00:00Z"
source: "https://github.com/olivecasazza/nixlab/blob/abc1234/README.md"
---

How we route game traffic through the hetzner-relay into Cilium NodePort.
"""


def load_tool():
    spec = importlib.util.spec_from_file_location("vault_classify", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    tool = load_tool()
    dests = ["personal", "projects", "cluster", "reference", "research", "journal", "docs", "archive"]

    # 1. Frontmatter parse: tags survive as a list, body is separated.
    fm, body = tool.parse_frontmatter(NOTE)
    assert fm["tags"] == ["networking", "k8s"], "tags not parsed as a list"
    assert "ingested_at" in fm, "ingested_at not parsed"
    assert body.startswith("How we route"), "body not split from frontmatter"

    # 2. Payload construction: valid OpenAI chat shape, deterministic, no creativity.
    payload = tool.build_payload(fm, body, model="claude-sonnet-4-6", destinations=dests)
    assert payload["model"] == "claude-sonnet-4-6", "model not set"
    assert payload["temperature"] == 0, "classifier must be deterministic (temp 0)"
    assert payload["max_tokens"] == 10, "one-word answer => small max_tokens"
    roles = [m["role"] for m in payload["messages"]]
    assert roles == ["system", "user"], "expected [system, user] messages"
    assert ", ".join(dests) in payload["messages"][0]["content"], "destinations not injected into system prompt"
    user = payload["messages"][1]["content"]
    assert "Tags: ['networking', 'k8s']" in user, "tags not echoed into the user message"
    assert "How we route" in user, "body snippet not included in the user message"
    # Snippet is bounded to 4000 chars (plus the Tags: prefix line).
    assert len(user) <= 4000 + 64, "body snippet not truncated to 4000 chars"
    json.dumps(payload)  # must be JSON-serializable

    # 3. Normalization: clean answers map through; messy answers get sanitized;
    #    unknown answers fall back to "reference".
    assert tool.normalize_category("cluster", dests) == "cluster", "exact category lost"
    assert tool.normalize_category("  Cluster\n", dests) == "cluster", "whitespace/case not normalized"
    assert tool.normalize_category("research.", dests) == "research", "punctuation not stripped"
    # "Category: journal" -> strip non-[a-z] -> "categoryjournal", not a valid
    # category, so it falls back rather than accidentally matching "journal".
    assert tool.normalize_category("Category: journal", dests) == "reference", "run-together multi-word answer did not fall back"
    assert tool.normalize_category("frobnicate", dests) == "reference", "unknown category did not fall back to reference"
    assert tool.normalize_category("", dests) == "reference", "empty answer did not fall back"

    # 4. Stamping: adds the category tag + status, never duplicates category tags,
    #    and does not mutate the caller's dict.
    fm2 = dict(fm)
    fm2["tags"] = ["networking", "category/reference"]
    stamped = tool.stamp(fm2, body, "cluster")
    assert stamped["enrichment_status"] == "classified", "enrichment_status not set"
    assert "classified_at" in stamped, "classified_at not stamped"
    cat_tags = [t for t in stamped["tags"] if str(t).startswith("category/")]
    assert cat_tags == ["category/cluster"], f"expected exactly one category tag, got {cat_tags}"
    assert fm2["tags"] == ["networking", "category/reference"], "stamp mutated the input frontmatter"

    # 5. Rendered note round-trips back through the parser with frontmatter intact.
    rendered = tool.render_note(stamped, body)
    rfm, rbody = tool.parse_frontmatter(rendered)
    assert rfm["enrichment_status"] == "classified", "rendered note lost stamp"
    assert rbody.startswith("How we route"), "rendered note lost body"

    print("vault-classify eval: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        sys.exit(f"vault-classify eval FAILED: {e}")

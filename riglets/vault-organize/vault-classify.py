#!/usr/bin/env python3
"""vault-classify — classify an Obsidian note into category/tags/entities/summary.

The agent-facing front end to the nixlab "langgraph-organize" pipeline. The old
deployment was a CronJob running a LangGraph graph (scan inbox -> classify via
LiteLLM -> write Neo4j -> move file). LiteLLM:4000 is dead and the graph
machinery is overkill: the load-bearing step is a single strict-JSON
classification call. This tool is that step, repointed at cliproxyapi.

It reads ONE markdown note, strips YAML frontmatter, builds a chat/completions
payload, calls the cliproxyapi gateway, and prints the normalized classification
JSON on stdout. The agent decides what to do with the verdict (move the file,
update frontmatter, MERGE into Neo4j) — those side effects stay out of the tool.

Usage:
  vault-classify --file inbox/note.md
  vault-classify -f note.md --model gpt-5.5 --url http://cliproxyapi.apps.svc.cluster.local:8317/v1

Auth: Bearer token from $ANTHROPIC_API_KEY (the cliproxyapi key). Stdlib only.
"""
import argparse
import json
import os
import re
import sys
import urllib.request

DEFAULT_URL = os.environ.get(
    "CLIPROXY_URL", "http://cliproxyapi.apps.svc.cluster.local:8317/v1"
)
DEFAULT_MODEL = os.environ.get("VAULT_MODEL", "gemini-3-flash-preview")

# Mirrors VALID_CATEGORIES from the original organize.py graph.
VALID_CATEGORIES = {
    "docs",
    "research",
    "personal",
    "projects",
    "reference",
    "archive",
}
FALLBACK_CATEGORY = "reference"

CLASSIFY_PROMPT = """\
You are a knowledge-management assistant. Read the note below and return ONLY
valid JSON with these fields:
  category  — one of: docs, research, personal, projects, reference, archive
  tags      — list of 2-6 short lowercase strings
  entities  — list of {{name, type}} objects (people, tools, concepts, places)
  summary   — one sentence, <=120 chars

Note content:
---
{content}
---

Return ONLY the JSON object, no markdown fences.
"""

# Strip a leading YAML frontmatter block (--- ... ---) without a yaml dep.
_FRONTMATTER = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
# Strip ```json ... ``` fences a model may emit despite instructions.
_FENCE = re.compile(r"\A\s*```(?:json)?\s*\n(.*?)\n```\s*\Z", re.DOTALL)


def strip_frontmatter(text):
    """Drop a leading YAML frontmatter block; return the note body."""
    return _FRONTMATTER.sub("", text, count=1).strip()


def build_payload(content, model):
    """Build the chat/completions request body for one note.

    Content is truncated to 8000 chars (matches the original graph; vault
    classification on truncated content is well within model capability).
    """
    body = content.strip() or "(empty note)"
    return {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "user", "content": CLASSIFY_PROMPT.format(content=body[:8000])},
        ],
    }


def parse_classification(raw):
    """Parse + normalize a model's classification reply into the vault schema.

    Tolerates code fences. Validates category against VALID_CATEGORIES,
    defaulting unknown/missing to 'reference'. Guarantees the four fields are
    present and well-typed so downstream Neo4j/frontmatter writes are safe.
    """
    text = raw.strip()
    m = _FENCE.match(text)
    if m:
        text = m.group(1).strip()
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("classification reply is not a JSON object")

    category = result.get("category", FALLBACK_CATEGORY)
    if category not in VALID_CATEGORIES:
        category = FALLBACK_CATEGORY

    tags = result.get("tags") or []
    if not isinstance(tags, list):
        tags = []

    entities = result.get("entities") or []
    if not isinstance(entities, list):
        entities = []

    summary = result.get("summary") or ""
    if not isinstance(summary, str):
        summary = str(summary)

    return {
        "category": category,
        "tags": [str(t) for t in tags],
        "entities": [
            {"name": str(e.get("name", "")), "type": str(e.get("type", "unknown"))}
            for e in entities
            if isinstance(e, dict)
        ],
        "summary": summary[:120],
    }


def call(url, payload, api_key):
    req = urllib.request.Request(
        f"{url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read())
    return resp["choices"][0]["message"]["content"]


def main():
    ap = argparse.ArgumentParser(
        description="Classify an Obsidian note (category/tags/entities/summary)."
    )
    ap.add_argument("-f", "--file", required=True, help="Path to the markdown note")
    ap.add_argument(
        "-m", "--model", default=DEFAULT_MODEL, help=f"Model (default: {DEFAULT_MODEL})"
    )
    ap.add_argument(
        "-u", "--url", default=DEFAULT_URL, help=f"cliproxyapi base URL (default: {DEFAULT_URL})"
    )
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY (cliproxyapi key) is not set")

    with open(args.file, encoding="utf-8") as fh:
        body = strip_frontmatter(fh.read())

    payload = build_payload(body, args.model)
    try:
        raw = call(args.url, payload, api_key)
    except Exception as exc:
        sys.exit(f"classify request failed: {exc}")

    try:
        verdict = parse_classification(raw)
    except Exception as exc:
        sys.exit(f"could not parse classification: {exc}\nraw: {raw!r}")

    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()

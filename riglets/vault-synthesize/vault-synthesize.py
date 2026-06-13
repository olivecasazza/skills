#!/usr/bin/env python3
"""vault-synthesize — synthesize an Obsidian "concept" note from related notes.

The agent-facing front end to the nixlab Vault Dreamer's ConsolidatorExpert. The
original ran on a 2h CronJob: it clustered similar notes via pgvector, then asked
an LLM to write a concept summary. This tool keeps the valuable half — the LLM
synthesis — and hands the *clustering* back to the agent, which is better at
deciding which notes belong together. You pass the notes; it writes the concept.

Usage:
  vault-synthesize --note a.md --note b.md --note c.md --note d.md
  vault-synthesize -n a.md -n b.md -n c.md -n d.md --out _concepts --vault /vault
  vault-synthesize -n a.md -n b.md ... --model claude-sonnet-4-6 --dry-run

Backend: the in-cluster cliproxyapi gateway (chat/completions), NOT the dead
litellm:4000. Auth is a Bearer token from $ANTHROPIC_API_KEY.

Pure logic (payload build, response parse, concept assembly) is factored out of
the network path so it can be tested offline — see evals/vault-synthesize/test.py.
"""
import argparse
import hashlib
import json
import os
import pathlib
import sys
import urllib.request

DEFAULT_URL = os.environ.get(
    "CLIPROXY_URL", "http://cliproxyapi.apps.svc.cluster.local:8317/v1"
)
DEFAULT_MODEL = os.environ.get("VAULT_SYNTH_MODEL", "claude-sonnet-4-6")

SYSTEM_PROMPT = (
    "Synthesize a 200-word concept summary from these notes. "
    "Write tightly. End with a 'Members' bullet list of "
    "[[wiki-links|titles]]."
)


# ---------------------------------------------------------------------------
# Pure helpers (no I/O) — these carry the tested contract.
# ---------------------------------------------------------------------------


def concept_slug(members):
    """Deterministic 8-char slug over the SORTED member set.

    Order-independent so the same cluster always maps to the same concept file
    (idempotency), matching the original ConsolidatorExpert._write_concept.
    """
    return hashlib.sha1("".join(sorted(members)).encode()).hexdigest()[:8]


def build_payload(snippets, model=DEFAULT_MODEL):
    """Build the chat/completions request body from per-note snippets.

    `snippets` is a list of pre-formatted strings (one per member note). The user
    message joins them with a divider, mirroring the dreamer's batch prompt.
    """
    user_msg = "\n\n---\n\n".join(snippets)
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 400,
    }


def parse_response(api_json):
    """Pull the assistant text out of a chat/completions response dict."""
    return api_json["choices"][0]["message"]["content"].strip()


def wiki_links(members):
    """[[path|stem]] link for each member, preserving order."""
    return [f"[[{m}|{pathlib.Path(m).stem}]]" for m in members]


def assemble_concept(members, body_text, generated_at):
    """Return (frontmatter_dict, body_str) for a concept note.

    Frontmatter shape matches the dreamer's _concepts/*.md notes so the two
    producers stay interchangeable. The body is the LLM text; if it did not end
    with member links, we append them so the concept is always navigable.
    """
    fm = {
        "tags": ["concept", "auto-generated"],
        "slug": concept_slug(members),
        "members": members,
        "generated_at": generated_at,
    }
    body = body_text
    if "[[" not in body:
        body = body.rstrip() + "\n\n## Members\n\n" + "\n".join(
            f"- {link}" for link in wiki_links(members)
        )
    return fm, body


def render_note(fm, body):
    """Serialize frontmatter + body to the dreamer's note format (JSON values)."""
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {json.dumps(v)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + "\n" + body + "\n"


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def read_snippet(vault, rel, limit=1500):
    """Read a vault note and format it as a synthesis snippet (title + excerpt)."""
    path = (vault / rel) if vault else pathlib.Path(rel)
    text = path.read_text(errors="replace")
    title = path.stem
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                if line.startswith("title: "):
                    try:
                        title = json.loads(line[len("title: "):].strip())
                    except Exception:
                        title = line[len("title: "):].strip()
            body = text[end + 4:].lstrip("\n")
    return f"### {title}\n\n{body[:limit]}"


def post(url, body, token, timeout=120):
    req = urllib.request.Request(
        url,
        json.dumps(body).encode(),
        {"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def now_iso():
    import datetime

    return datetime.datetime.utcnow().isoformat() + "Z"


def main():
    ap = argparse.ArgumentParser(description="Synthesize a concept note from related vault notes.")
    ap.add_argument("-n", "--note", action="append", default=[], required=True,
                    help="Vault-relative path to a member note (repeat, >= 2)")
    ap.add_argument("--vault", help="Vault root; notes are resolved relative to it (default: CWD)")
    ap.add_argument("-o", "--out", default="_concepts",
                    help="Output dir under the vault (default: _concepts)")
    ap.add_argument("-u", "--url", default=DEFAULT_URL, help=f"chat/completions base (default: {DEFAULT_URL})")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Model (default: {DEFAULT_MODEL})")
    ap.add_argument("--dry-run", action="store_true", help="Print the note instead of writing it")
    args = ap.parse_args()

    members = list(args.note)
    if len(members) < 2:
        sys.exit("need at least 2 --note members to synthesize a concept")

    vault = pathlib.Path(args.vault) if args.vault else None

    snippets = []
    for rel in members:
        try:
            snippets.append(read_snippet(vault, rel))
        except Exception as e:
            print(f"warning: could not read {rel}: {e}", file=sys.stderr)
    if not snippets:
        sys.exit("no readable member notes")

    token = os.environ.get("ANTHROPIC_API_KEY", "")
    if not token:
        sys.exit("ANTHROPIC_API_KEY unset (cliproxyapi Bearer token)")

    payload = build_payload(snippets, args.model)
    resp = post(f"{args.url}/chat/completions", payload, token)
    body_text = parse_response(resp)

    fm, body = assemble_concept(members, body_text, now_iso())
    note = render_note(fm, body)

    if args.dry_run:
        sys.stdout.write(note)
        return

    base = vault if vault else pathlib.Path(".")
    out_dir = base / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{fm['slug']}.md"
    dest.write_text(note)
    print(str(dest))


if __name__ == "__main__":
    main()

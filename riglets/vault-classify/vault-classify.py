#!/usr/bin/env python3
"""vault-classify — classify an Obsidian note into a vault category folder.

The agent-facing front end to the nixlab `ingest` app's LLM classifier. The app
runs this logic as a 4-hourly K8s CronJob (vault-classify) that drains inbox/
notes into category folders. This tool exposes the same single-note decision so
an agent can classify (and optionally route) one note on demand.

Given a markdown note (frontmatter + body), it asks the chat backend
(cliproxyapi, OpenAI-compatible /v1/chat/completions) to pick ONE category from
a fixed destination set, normalizes the model's answer, and prints the category.
With --apply it also moves the note + its .embeddings.json sidecar into
<vault>/<category>/ and stamps the frontmatter (category/<cat> tag,
enrichment_status=classified, classified_at).

Usage:
  vault-classify note.md
  vault-classify note.md --apply --vault /mnt/seaweedfs/obsidian-vault
  cat note.md | vault-classify -            # read from stdin, classify only
  vault-classify note.md --model gpt-5.5 --url http://host:8317/v1

Stdlib only (urllib/json/argparse). Auth: Bearer from --key or $ANTHROPIC_API_KEY.
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import shutil
import sys
import urllib.request

DEFAULT_URL = os.environ.get(
    "CHAT_URL", "http://cliproxyapi.apps.svc.cluster.local:8317/v1"
)
DEFAULT_MODEL = os.environ.get("CLASSIFY_MODEL", "claude-sonnet-4-6")
DEFAULT_DESTINATIONS = os.environ.get(
    "CLASSIFY_DESTINATIONS",
    "personal,projects,cluster,reference,research,journal,docs,archive",
).split(",")
FALLBACK = "reference"

# The classifier system prompt — kept in lockstep with the ingest app's
# vault-classify CronJob so the agent and the cron make the same decisions.
CLASSIFY_PROMPT = """\
You are a personal knowledge management assistant. Given the frontmatter tags \
and the opening of a note, decide which top-level folder it belongs in.

Available categories:
{categories}

Rules:
- personal     : personal notes, journal entries, reflections, todo lists
- projects     : active application/library project work that is NOT cluster
                 infrastructure (web/3D apps, libraries, tools)
- cluster      : nixlab infrastructure work — K8s, NixOS host configs, fleet
                 orchestration, CI/CD, SOPS/secrets, networking, storage,
                 observability. Anything running ON or deploying TO the cluster.
- reference    : reference material, docs, how-tos, specs not tied to a project
- research     : papers, academic content, deep external technical exploration
- journal      : dated diary/log entries, retros, standup notes
- docs         : project-internal documentation that is part of a repo's docs
- archive      : outdated, deprecated, or completed content to deprioritise

Respond with ONLY the category name, nothing else. One word.\
"""


def parse_frontmatter(text):
    """Split a markdown note into (frontmatter dict, body). Mirrors the app."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    fm = {}
    for line in text[4:end].splitlines():
        if ": " in line:
            k, _, v = line.partition(": ")
            try:
                fm[k.strip()] = json.loads(v.strip())
            except Exception:
                fm[k.strip()] = v.strip()
    body = text[end + 4:].lstrip("\n")
    return fm, body


def build_payload(fm, body, model=DEFAULT_MODEL, destinations=None):
    """Construct the OpenAI-compatible /v1/chat/completions request body.

    Pure: deterministic given inputs. This is the core contract the eval pins.
    """
    destinations = destinations or DEFAULT_DESTINATIONS
    tags = fm.get("tags", [])
    snippet = body[:4000]
    system = CLASSIFY_PROMPT.format(categories=", ".join(destinations))
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Tags: {tags}\n\n{snippet}"},
        ],
        "max_tokens": 10,
        "temperature": 0,
    }


def normalize_category(raw, destinations=None):
    """Map a raw model response to a valid category, else fall back.

    Pure: strips to lowercase letters and validates against the destination set.
    """
    destinations = destinations or DEFAULT_DESTINATIONS
    cat = re.sub(r"[^a-z]", "", str(raw).strip().lower())
    if cat not in destinations:
        return FALLBACK
    return cat


def _post(url, payload, key, timeout=60):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url + "/chat/completions", body, headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def classify(fm, body, url, model, key, destinations):
    payload = build_payload(fm, body, model, destinations)
    resp = _post(url, payload, key)
    raw = resp["choices"][0]["message"]["content"]
    return normalize_category(raw, destinations)


def stamp(fm, body, category):
    """Return updated frontmatter dict with classification fields applied. Pure."""
    fm = dict(fm)
    tags = [t for t in list(fm.get("tags", [])) if not str(t).startswith("category/")]
    tags.append(f"category/{category}")
    fm["tags"] = tags
    fm["enrichment_status"] = "classified"
    fm["classified_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    return fm


def render_note(fm, body):
    out = ["---"]
    for k, v in fm.items():
        out.append(f"{k}: {json.dumps(v)}")
    out.append("---\n")
    return "\n".join(out) + "\n" + body


def main():
    ap = argparse.ArgumentParser(description="Classify an Obsidian note into a vault category.")
    ap.add_argument("note", help="Path to the .md note, or '-' to read from stdin (classify only)")
    ap.add_argument("--apply", action="store_true", help="Move + stamp the note into <vault>/<category>/")
    ap.add_argument("--vault", default=os.environ.get("VAULT", "/mnt/seaweedfs/obsidian-vault"),
                    help="Vault root (for --apply)")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Chat model (default: {DEFAULT_MODEL})")
    ap.add_argument("-u", "--url", default=DEFAULT_URL, help=f"Chat base URL (default: {DEFAULT_URL})")
    ap.add_argument("--key", default=os.environ.get("ANTHROPIC_API_KEY", ""), help="Bearer key (default: $ANTHROPIC_API_KEY)")
    ap.add_argument("--destinations", default=",".join(DEFAULT_DESTINATIONS),
                    help="Comma-separated category set")
    args = ap.parse_args()
    destinations = args.destinations.split(",")

    if args.note == "-":
        fm, body = parse_frontmatter(sys.stdin.read())
        print(classify(fm, body, args.url, args.model, args.key, destinations))
        return

    path = pathlib.Path(args.note)
    fm, body = parse_frontmatter(path.read_text(errors="replace"))
    cat = classify(fm, body, args.url, args.model, args.key, destinations)

    if not args.apply:
        print(cat)
        return

    fm = stamp(fm, body, cat)
    dest_dir = pathlib.Path(args.vault) / cat
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if dest.exists() and dest.resolve() != path.resolve():
        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        dest = dest_dir / f"{path.stem}-{ts}{path.suffix}"
    dest.write_text(render_note(fm, body))
    if dest.resolve() != path.resolve():
        path.unlink()
        sidecar = path.with_suffix(".embeddings.json")
        if sidecar.exists():
            shutil.move(str(sidecar), str(dest.with_suffix(".embeddings.json")))
    print(f"{cat}\t{dest}")


if __name__ == "__main__":
    main()

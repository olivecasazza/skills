#!/usr/bin/env python3
"""comfyui-generate — submit a ComfyUI workflow, wait, and download the outputs.

The agent-facing front end to the nixlab ComfyUI backend. Replaces the ComfyUI
web node-graph UI: you hand it a workflow JSON (a saved /prompt graph) plus
optional prompt/seed overrides, and it blocks until the images land in the CWD.

Usage:
  comfyui-generate --workflow gothic-lettering.json --prompt "blackletter A" \
                   --out ./renders
  comfyui-generate -w wf.json --seed 42 --url http://comfyui.apps.svc.cluster.local:8188

The workflow JSON is the ComfyUI *API format* (node-id -> {class_type, inputs}),
i.e. what the web UI exports via "Save (API Format)". --prompt / --seed patch the
first CLIPTextEncode positive node and the first KSampler seed if present.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import uuid

DEFAULT_URL = os.environ.get("COMFY_URL", "http://comfyui.apps.svc.cluster.local:8188")


def _req(url, data=None, raw=False):
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    with urllib.request.urlopen(urllib.request.Request(url, body, headers), timeout=120) as r:
        return r.read() if raw else json.loads(r.read())


def patch(graph, prompt, seed):
    """Patch the positive prompt and sampler seed into an API-format graph."""
    seen_text = False
    for node in graph.values():
        ct, ins = node.get("class_type"), node.get("inputs", {})
        if prompt and not seen_text and ct == "CLIPTextEncode" and "text" in ins:
            ins["text"] = prompt  # first CLIPTextEncode is the positive prompt by convention
            seen_text = True
        if seed is not None and "seed" in ins:
            ins["seed"] = seed
    if prompt and not seen_text:
        print("warning: no CLIPTextEncode node found to apply --prompt", file=sys.stderr)
    return graph


def main():
    ap = argparse.ArgumentParser(description="Submit a ComfyUI workflow and download outputs.")
    ap.add_argument("-w", "--workflow", required=True, help="Workflow JSON (ComfyUI API format)")
    ap.add_argument("-p", "--prompt", help="Override the positive prompt text")
    ap.add_argument("-s", "--seed", type=int, help="Override the sampler seed")
    ap.add_argument("-o", "--out", default=".", help="Output directory (default: CWD)")
    ap.add_argument("-u", "--url", default=DEFAULT_URL, help=f"ComfyUI base URL (default: {DEFAULT_URL})")
    ap.add_argument("--timeout", type=int, default=600, help="Max seconds to wait (default: 600)")
    args = ap.parse_args()

    with open(args.workflow) as f:
        graph = json.load(f)
    graph = patch(graph, args.prompt, args.seed)

    client_id = str(uuid.uuid4())
    pid = _req(f"{args.url}/prompt", {"prompt": graph, "client_id": client_id})["prompt_id"]
    print(f"submitted prompt_id={pid}", file=sys.stderr)

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        hist = _req(f"{args.url}/history/{pid}").get(pid)
        if hist:
            status = hist.get("status", {}).get("status_str")
            if status == "success":
                break
            if status == "error":
                sys.exit(f"generation failed: {json.dumps(hist.get('status'))}")
        time.sleep(2)
    else:
        sys.exit(f"timed out after {args.timeout}s waiting for {pid}")

    os.makedirs(args.out, exist_ok=True)
    saved = []
    for node_out in hist.get("outputs", {}).values():
        for img in node_out.get("images", []):
            q = urllib.parse.urlencode(
                {"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")}
            )
            dest = os.path.join(args.out, img["filename"])
            with open(dest, "wb") as f:
                f.write(_req(f"{args.url}/view?{q}", raw=True))
            saved.append(dest)
            print(dest)
    if not saved:
        sys.exit("generation succeeded but produced no images")


if __name__ == "__main__":
    main()

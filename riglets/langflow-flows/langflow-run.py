#!/usr/bin/env python3
"""langflow-run — invoke a Langflow flow via the run API and print its output.

The agent-facing front end to the nixlab Langflow backend. Replaces the Langflow
Playground / IDE chat surface: instead of opening a flow in the browser and typing
into the chat panel, you hand this tool a flow id (or endpoint name) plus an input
string, and it POSTs to the run API, blocks on the result, and prints the flow's
text output to stdout.

Usage:
  langflow-run --list
  langflow-run --flow f2c0a000-0000-0000-0000-00000000ca20 --input "what is in the vault about k3s?"
  langflow-run -f MUTHA-VA -i "RTX 4000, 8GB, $300, eBay" --output-type chat

  # tweak a component's field at run time (repeatable):
  langflow-run -f <id> -i "..." --tweak ChatInput-abc.input_value="hello"

Flow addressing: `--flow` is either a flow UUID or a flow's endpoint_name. The two
nixlab RAG flows carry stable UUIDs:
  ingest -> f1c0a000-0000-0000-0000-00000000ca10
  rag    -> f2c0a000-0000-0000-0000-00000000ca20
The MUTHA-VA / OVHAF framework flows have no fixed id; run `--list` to discover the
id the backend assigned them after import.

Auth: LANGFLOW_AUTO_LOGIN=false, so the run API needs an `x-api-key`. Set
$LANGFLOW_API_KEY (mint one in the UI under Settings -> API Keys, or via
POST /api/v1/api_key/). Without it the backend returns 403.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get(
    "LANGFLOW_URL", "http://langflow-service.apps.svc.cluster.local:8080"
)


def build_payload(input_value, output_type="chat", input_type="chat", tweaks=None):
    """Build the JSON body for POST /api/v1/run/{flow}.

    Mirrors the Langflow run-API contract: a chat-style invocation passes the user
    text as `input_value` with matching input/output types, plus an optional
    `tweaks` map of {component_id: {field: value}} to override node fields per run.
    """
    payload = {
        "input_value": input_value,
        "output_type": output_type,
        "input_type": input_type,
    }
    if tweaks:
        payload["tweaks"] = tweaks
    return payload


def parse_tweaks(pairs):
    """Turn ['ChatInput-abc.input_value=hi', ...] into {comp: {field: value}}.

    Each pair is COMPONENT.FIELD=VALUE. Same component may appear multiple times;
    fields accumulate under it.
    """
    tweaks = {}
    for pair in pairs or []:
        if "=" not in pair or "." not in pair.split("=", 1)[0]:
            raise ValueError(f"bad --tweak {pair!r}; want COMPONENT.FIELD=VALUE")
        path, value = pair.split("=", 1)
        comp, field = path.split(".", 1)
        tweaks.setdefault(comp, {})[field] = value
    return tweaks


def parse_output(response):
    """Extract the flow's text output from a Langflow run response.

    The run response is deeply nested and Langflow has shifted the exact path
    across 1.x releases, so this walks defensively:

      response.outputs[i].outputs[j].results.message.text   (current)
      ...                            .results.message.data.text
      ...                            .outputs.message.message (older)
      ...                            .messages[k].message     (chat fallback)

    Returns a list of strings (one per output message found), in document order.
    Raises ValueError if the response carries no recognizable text output.
    """
    texts = []
    for run in response.get("outputs", []) or []:
        for out in run.get("outputs", []) or []:
            results = out.get("results", {}) or {}
            msg = results.get("message", {})
            if isinstance(msg, dict):
                if isinstance(msg.get("text"), str):
                    texts.append(msg["text"])
                    continue
                data = msg.get("data", {})
                if isinstance(data, dict) and isinstance(data.get("text"), str):
                    texts.append(data["text"])
                    continue
            legacy_outputs = out.get("outputs", {})
            legacy = legacy_outputs.get("message", {}) if isinstance(legacy_outputs, dict) else {}
            if isinstance(legacy, dict) and isinstance(legacy.get("message"), str):
                texts.append(legacy["message"])
                continue
            for m in out.get("messages", []) or []:
                if isinstance(m, dict) and isinstance(m.get("message"), str):
                    texts.append(m["message"])
    if not texts:
        raise ValueError(
            "no text output found in run response; shape may have changed — "
            f"top-level keys: {sorted(response)}"
        )
    return texts


def _req(url, method="GET", data=None, api_key=None, timeout=300):
    body = json.dumps(data).encode() if data is not None else None
    headers = {}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["x-api-key"] = api_key
    req = urllib.request.Request(url, body, headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        sys.exit(f"HTTP {e.code} from {url}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"cannot reach Langflow at {url}: {e.reason}")


def main():
    ap = argparse.ArgumentParser(description="Invoke a Langflow flow via the run API.")
    ap.add_argument("-f", "--flow", help="Flow UUID or endpoint_name")
    ap.add_argument("-i", "--input", help="Input value (the chat message / question)")
    ap.add_argument("--output-type", default="chat", help="Run output type (default: chat)")
    ap.add_argument("--input-type", default="chat", help="Run input type (default: chat)")
    ap.add_argument(
        "--tweak",
        action="append",
        default=[],
        help="Per-run field override COMPONENT.FIELD=VALUE (repeatable)",
    )
    ap.add_argument("--list", action="store_true", help="List flows (name -> id) and exit")
    ap.add_argument("-u", "--url", default=DEFAULT_URL, help=f"Langflow base URL (default: {DEFAULT_URL})")
    ap.add_argument("--json", action="store_true", help="Print the raw run response JSON")
    ap.add_argument("--timeout", type=int, default=300, help="Max seconds to wait (default: 300)")
    args = ap.parse_args()

    api_key = os.environ.get("LANGFLOW_API_KEY")

    if args.list:
        flows = _req(f"{args.url}/api/v1/flows/", api_key=api_key, timeout=args.timeout)
        for fl in flows if isinstance(flows, list) else flows.get("flows", []):
            print(f"{fl.get('id')}\t{fl.get('endpoint_name') or '-'}\t{fl.get('name')}")
        return

    if not args.flow or args.input is None:
        ap.error("--flow and --input are required unless --list is given")

    tweaks = parse_tweaks(args.tweak)
    payload = build_payload(args.input, args.output_type, args.input_type, tweaks)
    resp = _req(
        f"{args.url}/api/v1/run/{args.flow}",
        method="POST",
        data=payload,
        api_key=api_key,
        timeout=args.timeout,
    )

    if args.json:
        print(json.dumps(resp, indent=2))
        return

    for text in parse_output(resp):
        print(text)


if __name__ == "__main__":
    main()

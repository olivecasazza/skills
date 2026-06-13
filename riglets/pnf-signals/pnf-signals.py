#!/usr/bin/env python3
"""pnf-signals — drive the nixlab pnf-ops trading desk over its HTTP API.

The agent-facing interface to the PNF Trading backend. The pnf-ops service runs
the point-and-figure scans and holds the signal book (it has the `pnf` CLI and
market data — the agent pod does not). This tool is the thin client the desk's
agents (CIO / quants / risk / trader) use to trigger scans, read the signal
book, and gate trades.

  pnf-signals list [--status waiting_approval] [--limit 50]   # read the signal book
  pnf-signals scan                                            # trigger a fresh sector scan
  pnf-signals approve <id> [--note "..."] [--actor cio]
  pnf-signals reject  <id> [--note "..."] [--actor risk-manager]

Base URL: $PNF_OPS_URL or http://pnf-ops-metrics.apps.svc.cluster.local:8080
Stdlib only (urllib/json/argparse).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("PNF_OPS_URL", "http://pnf-ops-metrics.apps.svc.cluster.local:8080")


def list_url(base, status=None, limit=None):
    """Pure: build the GET /signals URL with optional query params."""
    q = []
    if status:
        q.append(f"status={status}")
    if limit:
        q.append(f"limit={int(limit)}")
    return f"{base.rstrip('/')}/signals" + ("?" + "&".join(q) if q else "")


def gate_url(base, signal_id, action):
    """Pure: build the POST /signals/{id}/{approve|reject} URL."""
    if action not in ("approve", "reject"):
        raise ValueError(f"action must be approve|reject, got {action!r}")
    return f"{base.rstrip('/')}/signals/{int(signal_id)}/{action}"


def _req(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def main():
    ap = argparse.ArgumentParser(description="Drive the pnf-ops trading desk over HTTP.")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"pnf-ops base URL (default: {DEFAULT_URL})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List the signal book")
    p_list.add_argument("--status", help="Filter by status (e.g. waiting_approval, approved)")
    p_list.add_argument("--limit", type=int, default=100)

    sub.add_parser("scan", help="Trigger a fresh sector scan")
    sub.add_parser("dispatch", help="Sweep approved signals (execute the dispatch pipeline)")

    for action in ("approve", "reject"):
        p = sub.add_parser(action, help=f"{action.capitalize()} a signal")
        p.add_argument("id", type=int)
        p.add_argument("--note", default="")
        p.add_argument("--actor", default="agent")

    args = ap.parse_args()

    if args.cmd == "list":
        print(json.dumps(_req(list_url(args.url, args.status, args.limit)), indent=2))
    elif args.cmd == "scan":
        print(json.dumps(_req(f"{args.url.rstrip('/')}/run/scan", method="POST", body={})))
    elif args.cmd == "dispatch":
        print(json.dumps(_req(f"{args.url.rstrip('/')}/run/dispatch", method="POST", body={})))
    elif args.cmd in ("approve", "reject"):
        print(json.dumps(_req(
            gate_url(args.url, args.id, args.cmd),
            method="POST",
            body={"actor": args.actor, "note": args.note},
        )))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        sys.exit(f"pnf-ops {e.code}: {e.read().decode(errors='replace')[:300]}")

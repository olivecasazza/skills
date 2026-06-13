#!/usr/bin/env python3
"""pnf-signals — run a point-and-figure sector scan, risk-gate it, emit decisions.

The agent-facing front end to the nixlab pnf-ops backend. It replaces the
SQLite + Discord + cron ops pipeline: instead of a daemon that scans every 4h,
posts to Discord, and waits for `!pnf approve`, an agent runs this tool on
demand, reads the structured candidates, and decides what to do.

Pipeline (identical signal logic to the original pnf-ops app):
  1. Run `pnf scan sectors -side both` (the PNF charting CLI).
  2. Parse the fixed-width table into signal rows (parse_scan).
  3. Optionally ask an LLM risk gate (cliproxyapi) to triage each row.
  4. Apply the deterministic gate (gate_decision): rr >= MIN_RR and
     confidence >= MIN_CONFIDENCE => approvable; else review/ignore.
  5. Print one JSON object: {"summary", "signals": [...]}.

Usage:
  pnf-signals                          # scan + LLM risk gate, print JSON
  pnf-signals --skip-model             # scan only, deterministic gate (no LLM)
  pnf-signals --raw scan.txt           # parse a saved scan instead of running pnf
  pnf-signals --min-rr 2.5 --model claude-sonnet-4-6

The LLM call goes to cliproxyapi (the litellm:4000 gateway is dead). It uses the
OpenAI-compatible /chat/completions endpoint with JSON mode — stdlib only, no
openai/instructor deps. The judge schema is enforced after the fact in
parse_decisions, so a malformed model reply degrades to "review", never crashes.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

PNF_CMD = os.environ.get("PNF_CMD", "pnf")
# cliproxyapi is the live gateway; litellm:4000 is retired.
LLM_URL = os.environ.get(
    "PNF_LLM_BASE_URL", "http://cliproxyapi.apps.svc.cluster.local:8317/v1"
)
MODEL = os.environ.get("PNF_MODEL", "claude-sonnet-4-6")
MIN_RR = float(os.environ.get("PNF_MIN_RR", "2.0"))
MIN_CONFIDENCE = float(os.environ.get("PNF_MIN_CONFIDENCE", "0.6"))

SECTORS = {
    "Consumer Staples", "Industrials", "Utilities", "Financials", "Technology",
    "Materials", "Consumer Discretionary", "Real Estate", "Energy",
    "Communication Services", "Health Care",
}


def parse_scan(text):
    """Parse `pnf scan sectors` output into signal rows.

    Each emitted row: ticker, sector, close, pattern, signal_date, objective,
    stop, rr, side. Malformed / header / stale lines are skipped silently — the
    scanner output is whitespace-delimited and noisy. Multi-word sectors
    (e.g. "Consumer Staples") are reconstructed against the known SECTORS set.
    """
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("Ticker") or line.startswith("-"):
            continue
        toks = line.split()
        if len(toks) < 8 or not re.fullmatch(r"[A-Z0-9]{1,6}", toks[0]):
            continue
        # The signal date anchors the numeric tail: date, objective, stop, rr.
        date_idx = None
        for i in range(len(toks) - 1, -1, -1):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", toks[i]):
                date_idx = i
                break
        if date_idx is None or date_idx + 3 >= len(toks):
            continue
        # `close` is the last float before the pattern words.
        close_idx = None
        for i in range(date_idx - 1, 0, -1):
            try:
                float(toks[i])
                close_idx = i
                break
            except Exception:
                pass
        if close_idx is None:
            continue
        sector = toks[1]
        for end in range(2, close_idx):
            candidate = " ".join(toks[1:end + 1])
            if candidate in SECTORS:
                sector = candidate
                break
        pattern = " ".join(toks[close_idx + 1:date_idx])
        try:
            rows.append({
                "ticker": toks[0],
                "sector": sector,
                "close": float(toks[close_idx]),
                "pattern": pattern,
                "signal_date": toks[date_idx],
                "objective": float(toks[date_idx + 1]),
                "stop": float(toks[date_idx + 2]),
                "rr": float(toks[date_idx + 3]),
                "side": "bearish" if "Breakdown" in pattern else "bullish",
            })
        except Exception:
            continue
    return rows


def gate_decision(row, model_signal, min_rr=MIN_RR, min_conf=MIN_CONFIDENCE,
                  allow_auto_approve=False):
    """Conservative deterministic risk gate over a parsed row + LLM hint.

    Returns the final status string. The LLM can only *narrow* — its "approve"
    is honored only when rr and confidence clear the floors AND auto-approve is
    explicitly enabled; otherwise the hardest the gate goes is "waiting_approval"
    (a human/agent must sign off). "ignore" from the model is always honored.
    """
    action = str((model_signal or {}).get("action", "review")).lower()
    confidence = float((model_signal or {}).get("confidence", 0.5) or 0.5)
    if action == "ignore":
        return "ignored", confidence
    if (action == "approve" and row["rr"] >= min_rr
            and confidence >= min_conf and allow_auto_approve):
        return "approved", confidence
    return "waiting_approval", confidence


def parse_decisions(content):
    """Coerce a model reply (JSON string) into {TICKER: signal_dict}.

    Tolerant: bad JSON or wrong shape yields {} so the deterministic gate still
    runs on every row with default 'review' hints.
    """
    try:
        data = json.loads(content)
    except Exception:
        return {}
    out = {}
    for sig in (data.get("signals") or []):
        ticker = str(sig.get("ticker", "")).upper()
        if ticker:
            out[ticker] = sig
    return out


def call_model(scan_text, rows, url=LLM_URL, model=MODEL):
    """Ask the LLM risk gate to triage rows. Returns {TICKER: signal} or {}."""
    key = (os.environ.get("ANTHROPIC_API_KEY")
           or os.environ.get("PNF_LLM_KEY")
           or os.environ.get("OPENAI_API_KEY"))
    if not key:
        print("no LLM key (ANTHROPIC_API_KEY) — deterministic gate only",
              file=sys.stderr)
        return {}
    schema = {
        "summary": "short summary",
        "signals": [{
            "ticker": "XLP", "action": "review|approve|ignore",
            "confidence": 0.75, "urgency": "low|medium|high",
            "notes": "short reason",
        }],
    }
    prompt = (
        f"You are a conservative PNF risk gate. Rules: never approve rr below "
        f"{MIN_RR}; ignore malformed or stale-looking rows; otherwise use review.\n"
        f"Return strict JSON only, matching this shape: {json.dumps(schema)}\n"
        f"Rows: {json.dumps(rows)}\nRaw output:\n{scan_text[:6000]}"
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode())
        return parse_decisions(data["choices"][0]["message"]["content"])
    except Exception as exc:
        print(f"LLM risk gate failed, deterministic gate only: {exc}",
              file=sys.stderr)
        return {}


def main():
    ap = argparse.ArgumentParser(
        description="Run a PNF sector scan, risk-gate it, emit JSON decisions.")
    ap.add_argument("--raw", help="Parse a saved scan file instead of running pnf")
    ap.add_argument("--skip-model", action="store_true",
                    help="Skip the LLM risk gate (deterministic only)")
    ap.add_argument("--min-rr", type=float, default=MIN_RR)
    ap.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--url", default=LLM_URL, help=f"LLM base URL (default: {LLM_URL})")
    ap.add_argument("--allow-auto-approve", action="store_true",
                    help="Permit the gate to auto-approve (default: human signs off)")
    args = ap.parse_args()

    if args.raw:
        with open(args.raw) as f:
            scan_text = f.read()
    else:
        proc = subprocess.run([PNF_CMD, "scan", "sectors", "-side", "both"],
                              text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=180, check=False)
        if proc.returncode != 0:
            sys.exit((proc.stderr or proc.stdout).strip() or "pnf scan failed")
        scan_text = proc.stdout

    rows = parse_scan(scan_text)
    decisions = {} if args.skip_model else call_model(
        scan_text, rows, url=args.url, model=args.model)

    signals = []
    for row in rows:
        hint = decisions.get(row["ticker"], {})
        status, confidence = gate_decision(
            row, hint, min_rr=args.min_rr, min_conf=args.min_confidence,
            allow_auto_approve=args.allow_auto_approve)
        signals.append(dict(
            row, status=status, confidence=confidence,
            notes=str(hint.get("notes", ""))[:1000]))

    actionable = [s for s in signals if s["status"] != "ignored"]
    print(json.dumps({
        "summary": f"{len(actionable)} actionable of {len(rows)} signals",
        "signals": signals,
    }, indent=2))


if __name__ == "__main__":
    main()

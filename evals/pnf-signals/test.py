#!/usr/bin/env python3
"""Deterministic eval for the pnf-signals skill.

Runs sandboxed (no network): loads the skill's `pnf-signals` tool and asserts
its two pure-logic contracts — the scan parser (parse_scan) and the
conservative risk gate (gate_decision). The behavioral half (does the LLM gate
make good calls against a live scan?) is the Archon/Instructor workflow in
behavioral.md, which needs the cliproxyapi backend.

Convention: every skill with deterministic guarantees gets evals/<skill>/test.py.
The flake auto-registers each as `checks.<system>.<skill>-eval`.
"""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "riglets" / "pnf-signals" / "pnf-signals.py"

# A representative `pnf scan sectors` table: a header, a separator, a bullish
# single-word-sector row, a bearish multi-word-sector row, and noise lines that
# must be skipped (blank, malformed, lowercase ticker).
SCAN_FIXTURE = """\
Ticker  Sector              Close   Pattern              Date        Obj     Stop    RR
------  ------              -----   -------              ----        ---     ----    --
XLP     Consumer Staples    74.50   Double Top Breakout  2026-06-10  82.00   71.00   2.14
XLE     Energy              91.20   Triple Bottom Breakdown 2026-06-11  80.00  95.00  2.75

garbage line that is not a signal
abc     lowercase ticker should be ignored 1 2 3 2026-06-12 4 5 6
"""


def load_tool():
    spec = importlib.util.spec_from_file_location("pnf_signals", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    tool = load_tool()

    # --- parse_scan ---------------------------------------------------------
    rows = tool.parse_scan(SCAN_FIXTURE)
    by_ticker = {r["ticker"]: r for r in rows}

    # 1. Only the two well-formed signal rows survive; noise is dropped.
    assert set(by_ticker) == {"XLP", "XLE"}, f"unexpected tickers: {set(by_ticker)}"

    # 2. Multi-word sectors reconstruct correctly.
    assert by_ticker["XLP"]["sector"] == "Consumer Staples", "multi-word sector lost"
    assert by_ticker["XLE"]["sector"] == "Energy", "single-word sector wrong"

    # 3. Numeric tail parsed in order: close, objective, stop, rr.
    xlp = by_ticker["XLP"]
    assert xlp["close"] == 74.50 and xlp["objective"] == 82.00, "numeric tail misparsed"
    assert xlp["stop"] == 71.00 and xlp["rr"] == 2.14, "stop/rr misparsed"
    assert xlp["signal_date"] == "2026-06-10", "date misparsed"

    # 4. Side inferred from pattern: Breakdown => bearish, else bullish.
    assert xlp["side"] == "bullish", "breakout should be bullish"
    assert by_ticker["XLE"]["side"] == "bearish", "breakdown should be bearish"

    # --- gate_decision ------------------------------------------------------
    # 5. Model 'ignore' is always honored.
    status, _ = tool.gate_decision(xlp, {"action": "ignore", "confidence": 0.9})
    assert status == "ignored", "ignore not honored"

    # 6. 'approve' below the rr floor never auto-approves.
    low_rr = dict(xlp, rr=1.0)
    status, _ = tool.gate_decision(
        low_rr, {"action": "approve", "confidence": 0.99},
        min_rr=2.0, allow_auto_approve=True)
    assert status == "waiting_approval", "approved below rr floor"

    # 7. 'approve' clearing both floors still needs auto-approve enabled.
    good = {"action": "approve", "confidence": 0.9}
    status, _ = tool.gate_decision(xlp, good, min_rr=2.0, min_conf=0.6,
                                   allow_auto_approve=False)
    assert status == "waiting_approval", "auto-approved without opt-in"
    status, _ = tool.gate_decision(xlp, good, min_rr=2.0, min_conf=0.6,
                                   allow_auto_approve=True)
    assert status == "approved", "did not auto-approve when allowed and clearing floors"

    # 8. Default/no model hint => review (waiting_approval), not approved.
    status, conf = tool.gate_decision(xlp, {})
    assert status == "waiting_approval" and conf == 0.5, "default gate wrong"

    # --- parse_decisions ----------------------------------------------------
    # 9. Tolerant model-reply parsing: bad JSON degrades to {}.
    assert tool.parse_decisions("not json at all") == {}, "bad JSON not tolerated"
    decisions = tool.parse_decisions(json.dumps(
        {"summary": "x", "signals": [{"ticker": "xlp", "action": "ignore"}]}))
    assert decisions.get("XLP", {}).get("action") == "ignore", "ticker not upcased/indexed"

    print("pnf-signals eval: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        sys.exit(f"pnf-signals eval FAILED: {e}")

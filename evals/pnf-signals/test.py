#!/usr/bin/env python3
"""Deterministic eval for the pnf-signals skill.

Runs sandboxed (no network): loads the skill's `pnf-signals` tool and asserts its
pure URL-construction contract — the tool is a thin client of the pnf-ops HTTP API
(list / scan / approve / reject), so the logic worth pinning is that it builds the
right endpoints. The behavioral half (does the desk gate trades well?) is the
Archon/Instructor workflow in behavioral.md, against the live pnf-ops backend.

Convention: every skill with deterministic guarantees gets evals/<skill>/test.py.
The flake auto-registers each as `checks.<system>.<skill>-eval`.
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "riglets" / "pnf-signals" / "pnf-signals.py"
BASE = "http://pnf-ops-metrics.apps.svc.cluster.local:8080"


def load_tool():
    spec = importlib.util.spec_from_file_location("pnf_signals", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    tool = load_tool()

    # --- list_url -----------------------------------------------------------
    # 1. No filters -> bare /signals.
    assert tool.list_url(BASE) == f"{BASE}/signals", "bare list url wrong"
    # 2. status + limit -> query string.
    assert tool.list_url(BASE, status="waiting_approval", limit=50) == \
        f"{BASE}/signals?status=waiting_approval&limit=50", "filtered list url wrong"
    # 3. Trailing slash on base is normalized (no //).
    assert tool.list_url(BASE + "/") == f"{BASE}/signals", "trailing slash not normalized"

    # --- gate_url -----------------------------------------------------------
    # 4. approve/reject build the per-signal endpoint with an int id.
    assert tool.gate_url(BASE, 123, "approve") == f"{BASE}/signals/123/approve", "approve url wrong"
    assert tool.gate_url(BASE, "7", "reject") == f"{BASE}/signals/7/reject", "reject url (str id) wrong"

    # 5. An invalid action is rejected (guards against typo'd gates).
    try:
        tool.gate_url(BASE, 1, "delete")
        raise AssertionError("gate_url accepted an invalid action")
    except ValueError:
        pass

    print("pnf-signals eval: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        sys.exit(f"pnf-signals eval FAILED: {e}")

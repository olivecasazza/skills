#!/usr/bin/env python3
"""Deterministic eval for the dealbot-ovhaf skill.

Runs sandboxed (no network): loads the skill's `dealbot-evaluate` tool and asserts
its pure-logic contract — the OVHAF chat/completions payload is well-formed, the
model reply parser strips code fences, and the `should_alert` verdict gate honors
DealBot's buy/watch/reject rules (sold markers, RDIMM-vs-UDIMM rejection, and the
PSB/score/quotient threshold). This is the structural half; the behavioral half
(does the LLM produce a sound OVHAF verdict?) is the Archon/Instructor workflow in
behavioral.md, which needs the live cliproxyapi backend.

Convention: every skill with deterministic guarantees gets evals/<skill>/test.py.
The flake auto-registers each as `checks.<system>.<skill>-eval`.
"""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "riglets" / "dealbot-ovhaf" / "dealbot-evaluate.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("dealbot_evaluate", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    tool = load_tool()

    # 1. Payload construction is a valid chat/completions body, prompt carries the listing.
    deal = {
        "title": "AMD 5995WX + ASUS Pro WS WRX80E-SAGE combo",
        "source": "r/homelabsales",
        "url": "https://example.com/itm/123",
        "price_hint": "$1100",
        "text": "POSTs fine, CPU-Z attached, retail unlocked chip.",
    }
    payload = tool.build_payload(deal, "claude-sonnet-4-6")
    assert payload["model"] == "claude-sonnet-4-6", "model not set on payload"
    assert payload["messages"][0]["role"] == "user", "message role wrong"
    assert "OVHAF" in payload["messages"][0]["content"], "OVHAF framework missing from prompt"
    assert "5995WX" in payload["messages"][0]["content"], "listing title not embedded in prompt"
    json.dumps(payload)  # must be JSON-serializable

    # 2. Reply parser strips ```json fences and plain ``` fences.
    fenced = '```json\n{"recommendation": "BUY_NOW", "is_deal_good": true}\n```'
    parsed = tool._parse_json(fenced)
    assert parsed["recommendation"] == "BUY_NOW", "fenced JSON not parsed"
    assert tool._parse_json('{"x": 1}')["x"] == 1, "bare JSON not parsed"

    # 3. should_alert: explicit BUY_NOW / ASK_SELLER recommendations alert.
    assert tool.should_alert({"recommendation": "BUY_NOW"}) is True, "BUY_NOW must alert"
    assert tool.should_alert({"recommendation": "ASK_SELLER"}) is True, "ASK_SELLER must alert"
    assert tool.should_alert({"recommendation": "WATCH"}) is False, "bare WATCH must not alert"

    # 4. should_alert: sold/pending markers veto even a 'good' deal.
    sold = {"is_deal_good": True, "recommendation": "BUY_NOW", "summary": "Item sold/pending"}
    assert tool.should_alert(sold) is False, "sold marker must veto"

    # 5. should_alert: RDIMM-only memory is rejected; UDIMM passes the same threshold path.
    rdimm = {
        "recommendation": "WATCH",
        "summary": "DDR4 ECC RDIMM registered memory kit",
        "stage1": {"preliminary_ovhaf_score": 8},
        "stage2": {"psb_risk": "LOW"},
        "stage3": {"opti_value_quotient": 0.1},
    }
    assert tool.should_alert(rdimm) is False, "RDIMM-only memory must be vetoed"
    udimm = dict(rdimm, summary="DDR4 ECC UDIMM unbuffered memory kit")
    assert tool.should_alert(udimm) is True, "UDIMM at LOW psb / high score / high quotient must alert"

    # 6. should_alert: PSB/score/quotient threshold is conjunctive — below any bar, no alert.
    low_quotient = {
        "recommendation": "WATCH",
        "stage1": {"preliminary_ovhaf_score": 8},
        "stage2": {"psb_risk": "LOW"},
        "stage3": {"opti_value_quotient": 0.01},  # below 0.04
    }
    assert tool.should_alert(low_quotient) is False, "below quotient threshold must not alert"
    high_psb = dict(low_quotient, stage2={"psb_risk": "HIGH"}, stage3={"opti_value_quotient": 0.1})
    assert tool.should_alert(high_psb) is False, "HIGH psb must not clear the threshold path"

    print("dealbot-ovhaf eval: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        sys.exit(f"dealbot-ovhaf eval FAILED: {e}")

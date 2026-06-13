#!/usr/bin/env python3
"""dealbot-evaluate — score a used-hardware listing against the OVHAF framework.

The agent-facing front end to the nixlab DealBot capability. DealBot used to be a
CronJob that scraped marketplaces, evaluated each listing with an LLM, and pinged
Discord. This skill keeps the load-bearing brain — the Opti-Value Hardware
Acquisition Framework (OVHAF) evaluation — and exposes it as a tool the agent
drives. Scrape/notify are retired; the agent supplies the listing (paste, fetch,
or pipe) and gets back strict OVHAF JSON + a buy/watch/reject verdict.

Reads a listing from --file, --json, or stdin and POSTs an OVHAF prompt to the
cliproxyapi chat/completions gateway. Stdlib only (urllib/json/argparse) — no
openai package, no pip install.

Usage:
  dealbot-evaluate --title "5995WX + WRX80E-SAGE combo" --price "$1100" \
                   --text "POSTs fine, CPU-Z attached, ..." --url https://...
  cat listing.json | dealbot-evaluate            # {title,source,url,price_hint,text,flair}
  dealbot-evaluate --file listing.json --model claude-sonnet-4-6

Exit status: 0 if evaluated (regardless of verdict), non-zero only on usage/IO error.
"""
import argparse
import json
import os
import re
import sys
import urllib.request

# cliproxyapi chat/completions gateway (litellm:4000 is dead). Override with $DEALBOT_BASE_URL.
DEFAULT_URL = os.environ.get(
    "DEALBOT_BASE_URL", "http://cliproxyapi.apps.svc.cluster.local:8317/v1"
)
DEFAULT_MODEL = os.environ.get("DEALBOT_MODEL", "claude-sonnet-4-6")

OVHAF_PROMPT = """
You are DealBot v2, applying the Opti-Value Hardware Acquisition Framework (OVHAF) to used workstation hardware.

Target acquisition:
- Primary target: AMD Threadripper Pro 3000/5000 CPU + WRX80 motherboard combo, or EPYC Rome/Milan single socket (H12SSL/H11SSL), or enterprise workstations (Lenovo P620, Dell R7515, HP Z8) for ML workstation use. Also high-end Ada/Ampere GPUs (A5000, A6000, RTX 4090, RTX 6000 Ada, L40).
- Secondary urgent target: compatible RAM for contra, a workstation currently reporting ~16 GiB installed. Contra likely needs DDR4 ECC UDIMM memory, not registered/buffered RDIMM; prioritize exact compatibility listings such as DDR4 ECC UDIMM / unbuffered ECC 2666/2933/3200 and reject RDIMM/LRDIMM-only listings unless the listing clearly says compatible with the board in contra.
- Strong preference: retail/unlocked CPUs with non-OEM WRX80 boards (Gigabyte WRX80-SU8-IPMI, ASUS Pro WS WRX80E-SAGE SE WIFI, Supermicro WRX80 boards).
- Budget target: <= $1200 total cost of ownership for 3000-series combo; allow higher only for clearly superior 5000-series value.
- Critical risk: AMD PSB vendor lock. Lenovo P620 / Dell / HP OEM pulls are high risk unless the listing explicitly proves unlocked / board-compatible.
- ML relevance: 128 PCIe lanes, multiple GPU fit, IPMI, ECC RAM support, slot spacing, power/cooling/noise matter.
- HARD DISQUALIFIERS (MUST REJECT):
  1. Combo price vastly exceeds realistic market value (e.g. over $1200-$1500 for a 5995WX combo or heavily overpriced 3995WX).
  2. System fails to POST or indicates potential PSB vendor lock / dead component.
  3. Seller refuses to demonstrate the system working locally or refuses basic verifications.
- INACTIVE DEAL REJECTION: If the post explicitly states the Threadripper/WRX80 components have been sold, traded, or are pending payment, you must output `is_deal_good: false` and `recommendation: "REJECT"` with a reason of "Item sold/pending".

Apply OVHAF in exactly three stages.

Stage 1: Initial Filtering & Weighted Pillar Scoring
Score 1-10 for:
- technical_performance_relevance, weight 40
- verifiable_condition_reliability, weight 30
- seller_transaction_integrity, weight 20
- ancillary_value_long_term_costs, weight 10
Compute preliminary_ovhaf_score = weighted 1-10 score.

Stage 2: Deep-Dive Verification & Risk Mitigation
Assess missing/provided evidence:
- real-time proof/date card
- serials / CPU model proof
- POST/BIOS video
- CPU-Z/lscpu/HWiNFO proof
- stress/temperature proof
- board/CPU compatibility and PSB unlock proof
- return policy and shipping/insurance clarity
Produce specific seller_questions and disqualifiers.

Stage 3: Final Comparison & Optimal Value Calculation
Estimate:
- P normalized performance score 0-100
- L list price
- R risk multiplier, base 1.0 plus increments for missing evidence/risk
- A added costs: shipping, cooler, RAM, PSU, thermal paste, contingency
Calculate opti_value_quotient = P / ((L * R) + A)

Return strict JSON with these keys:
{
  "is_deal_good": boolean,
  "recommendation": "BUY_NOW" | "ASK_SELLER" | "WATCH" | "REJECT",
  "tier": "TIER_1_LIGHTWEIGHT" | "TIER_2_STANDARD" | "TIER_3_COMPREHENSIVE",
  "detected_hardware": {"cpu": string|null, "motherboard": string|null, "generation": string|null, "is_threadripper_pro": boolean, "is_wrx80": boolean},
  "stage1": {"technical_performance_relevance": number, "verifiable_condition_reliability": number, "seller_transaction_integrity": number, "ancillary_value_long_term_costs": number, "preliminary_ovhaf_score": number},
  "stage2": {"verification_status": "STRONG" | "PARTIAL" | "WEAK" | "MISSING", "psb_risk": "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN", "missing_evidence": [string], "seller_questions": [string], "disqualifiers": [string]},
  "stage3": {"P": number, "L": number, "R": number, "A": number, "opti_value_quotient": number, "tco_estimate": number},
  "summary": string,
  "reasoning": string
}

Be conservative. Reject or ASK_SELLER on unresolved PSB risk. Flag non-Pro Threadripper as poor for ML because it lacks 128 lanes.
"""


def build_prompt(deal):
    """Assemble the full OVHAF user prompt for one listing. Pure string building."""
    return f"""
{OVHAF_PROMPT}

DEAL DETAILS:
Title: {deal.get('title')}
Source: {deal.get('source')}
Link: {deal.get('url')}
Flair: {deal.get('flair', 'None')}
Price hint: {deal.get('price_hint')}
Description: {deal.get('text')}
"""


def build_payload(deal, model):
    """Construct the chat/completions request body. Pure dict building, no network."""
    return {
        "model": model,
        "messages": [{"role": "user", "content": build_prompt(deal)}],
        "response_format": {"type": "json_object"},
        "max_tokens": 3500,
    }


def _parse_json(content):
    """Tolerantly parse the model's reply: strip ```json fences, then json.loads."""
    if not content:
        raise ValueError("Empty response from LLM")
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\n", "", content)
        content = re.sub(r"\n```$", "", content)
    return json.loads(content)


def should_alert(eval_result):
    """Pure verdict gate: would DealBot surface this deal to a human?

    Mirrors the original CronJob's alert logic so the skill produces the same
    buy/watch decision without the Discord side effect.
    """
    rec = eval_result.get("recommendation")
    reason_blob = " ".join(
        [
            str(eval_result.get("summary", "")),
            str(eval_result.get("reasoning", "")),
            " ".join(eval_result.get("stage2", {}).get("disqualifiers", []) or []),
        ]
    ).lower()
    if any(
        marker in reason_blob
        for marker in (
            "sold",
            "pending",
            "closed",
            "complete",
            "no longer available",
            "traded",
            "vastly exceeds",
            "overpriced",
            "fails to post",
            "refuses to demonstrate",
            "dead component",
        )
    ):
        return False
    hardware_blob = " ".join(
        [
            str(eval_result.get("detected_hardware", {})),
            str(eval_result.get("summary", "")),
            str(eval_result.get("reasoning", "")),
        ]
    ).lower()
    if (
        "ecc" in hardware_blob
        or "ddr4" in hardware_blob
        or "memory" in hardware_blob
        or "ram" in hardware_blob
    ):
        if any(bad in hardware_blob for bad in ("rdimm", "lrdimm", "registered")) and not any(
            good in hardware_blob for good in ("udimm", "unbuffered")
        ):
            return False
    psb = eval_result.get("stage2", {}).get("psb_risk")
    quotient = eval_result.get("stage3", {}).get("opti_value_quotient", 0) or 0
    score = eval_result.get("stage1", {}).get("preliminary_ovhaf_score", 0) or 0
    return bool(
        eval_result.get("is_deal_good")
        or rec in ("BUY_NOW", "ASK_SELLER")
        or (psb in ("LOW", "MEDIUM") and score >= 5.5 and quotient >= 0.04)
    )


def _post(url, payload, api_key, timeout):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(f"{url}/chat/completions", body, headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    return resp["choices"][0]["message"]["content"]


def evaluate_deal(deal, url, model, api_key, timeout):
    """Run one OVHAF evaluation against the live gateway. Network happens here."""
    content = _post(url, build_payload(deal, model), api_key, timeout)
    return _parse_json(content)


def load_deal(args):
    """Resolve the listing from --file / --json / stdin / individual flags."""
    if args.file:
        with open(args.file) as f:
            return json.load(f)
    if args.json:
        return json.loads(args.json)
    if args.title:
        return {
            "title": args.title,
            "source": args.source,
            "url": args.url,
            "flair": args.flair,
            "price_hint": args.price,
            "text": args.text,
        }
    data = sys.stdin.read()
    if not data.strip():
        sys.exit("no listing provided: use --title/--file/--json or pipe JSON on stdin")
    return json.loads(data)


def main():
    ap = argparse.ArgumentParser(description="Evaluate a hardware listing with OVHAF.")
    ap.add_argument("--file", help="Path to a listing JSON file")
    ap.add_argument("--json", help="Listing as an inline JSON string")
    ap.add_argument("--title", help="Listing title (with --price/--text/--url)")
    ap.add_argument("--source", default="manual", help="Where the listing came from")
    ap.add_argument("--url", help="Listing URL")
    ap.add_argument("--flair", help="Listing flair, if any")
    ap.add_argument("--price", help="Price hint, e.g. '$1100'")
    ap.add_argument("--text", help="Listing body / description text")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"Model (default: {DEFAULT_MODEL})")
    ap.add_argument("-u", "--url-base", dest="base", default=DEFAULT_URL, help=f"Gateway base URL (default: {DEFAULT_URL})")
    ap.add_argument("--timeout", type=int, default=120, help="Request timeout seconds (default: 120)")
    args = ap.parse_args()

    deal = load_deal(args)
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("DEALBOT_API_KEY")
    result = evaluate_deal(deal, args.base, args.model, api_key, args.timeout)

    alert = should_alert(result)
    out = {
        "title": deal.get("title"),
        "url": deal.get("url"),
        "alert_worthy": alert,
        "evaluation": result,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

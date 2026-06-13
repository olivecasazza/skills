# DealBot OVHAF evaluation

The agent-facing interface to DealBot's brain — the **Opti-Value Hardware
Acquisition Framework (OVHAF)** evaluation. DealBot used to be a CronJob
that scraped marketplaces, scored each listing with an LLM, persisted state
in SQLite, and posted Discord cards. This skill REPLACES that pipeline's
decision core: you hand it one listing and it returns the same strict OVHAF
JSON verdict plus DealBot's alert/no-alert gate. The agent supplies the
listing (paste it, fetch it with WebFetch, or pipe scraped JSON); scraping
and Discord notification are retired.

## Tool: `dealbot-evaluate`

Reads a listing, POSTs an OVHAF prompt to the chat/completions gateway, and
prints `{title, url, alert_worthy, evaluation}` JSON on stdout.

```bash
dealbot-evaluate --title "5995WX + WRX80E-SAGE combo" --price '$1100' \
                 --text "POSTs fine, CPU-Z attached, retail unlocked" \
                 --url https://example.com/itm/123
# or pipe a listing object:
cat listing.json | dealbot-evaluate            # {title,source,url,price_hint,text,flair}
dealbot-evaluate --file listing.json --model gpt-5.5
```

- Listing fields: `title`, `source`, `url`, `price_hint`, `text`, `flair`.
  Provide via `--title/--price/--text/--url/--flair/--source`, `--json`,
  `--file`, or stdin JSON.
- `--model`: defaults to `$DEALBOT_MODEL` or `claude-sonnet-4-6`. The gateway
  also serves `gpt-5.5` and `gemini-3-flash-preview`.
- `--url-base`: chat/completions base URL. Defaults to `$DEALBOT_BASE_URL`
  or the in-cluster gateway
  `http://cliproxyapi.apps.svc.cluster.local:8317/v1`.
- Auth: `Authorization: Bearer $ANTHROPIC_API_KEY` (the cliproxyapi-secrets
  key). The litellm:4000 gateway is dead — do not point at it.

## Reading the output

- `evaluation.recommendation`: `BUY_NOW` | `ASK_SELLER` | `WATCH` | `REJECT`.
- `evaluation.stage2.psb_risk`: `HIGH` on OEM pulls means AMD PSB vendor
  lock is unproven — treat `HIGH` + no unlock proof as a REJECT regardless of
  price. Lenovo P620 / Dell / HP pulls are the usual traps.
- `evaluation.stage3.opti_value_quotient`: P / ((L·R) + A); higher is better
  value. The alert gate wants >= 0.04 alongside a >= 5.5 preliminary score
  and LOW/MEDIUM PSB risk.
- `alert_worthy`: DealBot's surface-to-human gate. False for sold/pending
  listings, RDIMM-only memory (contra needs **UDIMM** unbuffered ECC), and
  anything below the PSB/score/quotient bar. A BUY_NOW/ASK_SELLER is always
  alert-worthy.

## How it works (so you can debug)

1. `build_payload` wraps the listing in the OVHAF prompt → chat/completions body.
2. POST to `{base}/chat/completions` with the Bearer key.
3. `_parse_json` strips ```json fences (response_format is sent but not
   relied on — backends honor it inconsistently) and parses strict JSON.
4. `should_alert` applies DealBot's verdict gate (sold veto, RDIMM veto,
   PSB/score/quotient threshold).

If the gateway 401s, the `ANTHROPIC_API_KEY` env is missing/stale. If the
model returns prose instead of JSON, retry with a different `--model` or
re-state "return ONLY strict JSON".

## Out of scope

Marketplace scraping (Reddit/forums/eBay/Craigslist + TEI embedding
prefilter) and Discord alerting are retired with the CronJob. To evaluate a
live post, fetch it yourself (WebFetch) and pass the text in. The skill
scores one listing; it does not crawl, dedupe, or notify.

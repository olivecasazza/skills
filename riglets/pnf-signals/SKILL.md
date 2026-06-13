# PNF Trading desk control

The agent-facing client for the nixlab **pnf-ops** backend — the point-and-figure
trading desk. pnf-ops runs the scans (it has the `pnf` CLI and market data; the
agent pod does not) and holds the signal book in SQLite. You drive it over HTTP
with the `pnf-signals` tool: trigger a scan, read the book, gate trades.

This is the PNF Trading firm's interface. The desk's routines (Sector Scan Review,
Execution Sweep, Daily Desk Review) put work on your queue; you act with this tool.

## Tool: `pnf-signals`

```bash
pnf-signals list [--status waiting_approval] [--limit 50]   # read the signal book
pnf-signals scan                                            # trigger a fresh sector scan
pnf-signals approve <id> [--note "..."] [--actor cio]
pnf-signals reject  <id> [--note "..."] [--actor risk-manager]
pnf-signals dispatch                                        # sweep approved signals (trader)
```

The cron CronJobs are retired — scans and dispatch now run only when the desk
triggers them (via the routines → these commands). Nothing scans on its own.

Base URL: `$PNF_OPS_URL` or `http://pnf-ops-metrics.apps.svc.cluster.local:8080`.

## Desk workflow

1. **Scan** (or wait for the 4h cron): `pnf-signals scan` triggers a fresh
   point-and-figure sector scan; pnf-ops parses it, applies its own risk gate, and
   writes candidates to the book with `status=waiting_approval`.
2. **Read the book**: `pnf-signals list --status waiting_approval` returns the
   pending signals — ticker, sector, pattern, objective, stop, `rr` (reward:risk),
   side, confidence, notes.
3. **Quant review**: the three quants (Anthropic/OpenAI/Google) each independently
   assess every pending signal; the Risk Manager vetoes anything under the R/R floor
   or breaching limits; the CIO makes the call.
4. **Gate**: `pnf-signals approve <id>` / `reject <id>` (with `--actor` = your role
   and a `--note` rationale). Approved signals move to `status=approved`.
5. **Execute**: the Execution Trader sweeps approved signals (the pnf-ops dispatch
   pipeline acts on `status=approved`).

## Signal statuses

`waiting_approval` (needs the desk's decision) · `approved` (cleared for execution)
· `rejected` · `ignored` (gate dropped it) · `failed` (dispatch error).

## Notes

- No auth: pnf-ops-metrics is in-cluster only. From outside the cluster, set
  `--url` to a reachable address.
- This tool does not run `pnf` locally — pnf-ops owns the CLI, market data, and the
  signal book. You orchestrate; pnf-ops executes.

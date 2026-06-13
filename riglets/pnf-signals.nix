# First arg: the defining flake's `self` (unused).
_:
# Second arg: module args from evalModules.
{
  pkgs,
  riglib,
  ...
}:
let
  # The agent-facing front end to the nixlab pnf-ops backend. Stdlib-only Python
  # (urllib/subprocess/json), so no extra deps — just wrap it with python3.
  pnf-signals = pkgs.writeShellScriptBin "pnf-signals" ''
    exec ${pkgs.python3}/bin/python3 ${./pnf-signals/pnf-signals.py} "$@"
  '';
in
{
  config.riglets.pnf-signals = {
    meta = {
      description = "Run a point-and-figure sector scan, risk-gate it, and emit triaged trade-signal decisions (replaces the pnf-ops Discord/cron pipeline)";
      intent = "playbook";
      whenToUse = [
        "When asked to scan the market for point-and-figure (PNF) trade signals"
        "When triaging or reviewing PNF candidates and their risk/reward gate"
        "When the old pnf-ops Discord '!pnf' approve/reject loop would have been used"
      ];
      keywords = [
        "pnf"
        "point-and-figure"
        "trading"
        "signals"
        "risk-gate"
        "scan"
      ];
      status = "draft";
      version = "0.1.0";
    };

    tools = [ pnf-signals ];

    docs = riglib.writeFileTree {
      "SKILL.md" = ''
        # PNF trade-signal scan + risk gate

        The agent-facing interface to the nixlab pnf-ops backend (the `pnf`
        point-and-figure charting CLI). This skill REPLACES the standalone
        pnf-ops ops pipeline — the SQLite store, the 4-hourly scan CronJob, the
        Discord webhook alerts, and the `!pnf approve/reject` control loop. You,
        the agent, are the operator now: run a scan on demand, read the triaged
        candidates, and decide. The signal logic (scan parsing + conservative
        risk gate) is identical to the original app.

        ## Tool: `pnf-signals`

        Runs `pnf scan sectors -side both`, parses the table, asks an LLM risk
        gate to triage each row, applies the deterministic gate, and prints one
        JSON object to stdout.

        ```bash
        pnf-signals [--skip-model] [--raw scan.txt] \
                    [--min-rr N] [--min-confidence F] \
                    [--model M] [--url URL] [--allow-auto-approve]
        ```

        - `--skip-model`: skip the LLM gate; deterministic thresholds only.
        - `--raw FILE`: parse a saved scan dump instead of invoking `pnf`
          (useful offline / for replay).
        - `--min-rr` (default 2.0): never approve a signal whose reward:risk is
          below this floor.
        - `--min-confidence` (default 0.6): the LLM-confidence floor for approval.
        - `--allow-auto-approve`: permit the gate to emit `approved` directly.
          OFF by default — without it the hardest status is `waiting_approval`,
          i.e. a human/agent must sign off. Keep it off for anything live.
        - `--model` (default `claude-sonnet-4-6`) / `--url`: the LLM gate target.
          Defaults to cliproxyapi (`http://cliproxyapi.apps.svc.cluster.local:8317/v1`).
          The old litellm:4000 gateway is DEAD — do not point at it.

        ## Output shape

        ```json
        {
          "summary": "3 actionable of 11 signals",
          "signals": [
            {"ticker": "XLP", "sector": "Consumer Staples", "close": 74.5,
             "pattern": "Double Top Breakout", "signal_date": "2026-06-10",
             "objective": 82.0, "stop": 71.0, "rr": 2.14, "side": "bullish",
             "status": "waiting_approval", "confidence": 0.7, "notes": "..."}
          ]
        }
        ```

        `status` is one of: `waiting_approval`, `approved` (only with
        `--allow-auto-approve` and clearing the floors), `ignored`.

        ## How the gate decides (so you can reason about it)

        1. `pnf scan sectors -side both` produces a whitespace table.
        2. `parse_scan` extracts rows; noise/header/stale lines are dropped.
           `side` = bearish if the pattern contains "Breakdown", else bullish.
        3. The LLM risk gate (cliproxyapi, JSON mode) returns an `action`
           (`review`/`approve`/`ignore`), `confidence`, and `notes` per ticker.
           A malformed reply degrades gracefully — every row still gets the
           deterministic gate with a `review` default.
        4. `gate_decision` is conservative: the model can only narrow. `ignore`
           is honored; `approve` becomes `approved` ONLY if rr >= min-rr AND
           confidence >= min-confidence AND `--allow-auto-approve` is set;
           otherwise it is `waiting_approval`.

        ## Backend auth

        The LLM gate authenticates with `ANTHROPIC_API_KEY` (the cliproxyapi
        bearer, sourced from `cliproxyapi-secrets` in-cluster). With no key the
        tool prints a stderr warning and runs the deterministic gate only —
        scans still work, just without LLM triage.

        ## Out of scope

        Order execution. The original `dispatch` step only ran read-only
        `pnf TICKER --chart`; there is no broker integration. This skill produces
        and triages signals — acting on them is a human decision. Persistence
        (the SQLite runs/signals/approvals tables), Prometheus metrics, and
        Discord control are retired with the app; reach for them only if you are
        rebuilding the daemon, not driving a scan.
      '';
    };
  };
}

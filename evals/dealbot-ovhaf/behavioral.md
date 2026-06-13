# Behavioral eval — dealbot-ovhaf

The deterministic half (`test.py`) runs as a sandboxed `nix flake check` / `om ci`
and proves the payload/parse/verdict contract with no network. This file is the
**behavioral** half: given a real listing, does the agent (driving
`dealbot-evaluate` against the live cliproxyapi backend) produce a sound OVHAF
verdict? It needs the live gateway + an LLM judge, so it runs under **Archon** (the
workflow harness), not as a pure nix check.

## Contract

An Archon workflow feeds known listings through the skill and an **Instructor**-typed
judge scores whether the OVHAF output is internally consistent and matches the
ground-truth call. Eval cases live in `cases.toml` (when added); each case is a
listing + an expected disposition + a rubric.

### Archon workflow (sketch)

```yaml
# evals/dealbot-ovhaf/behavioral.archon.yaml  (run when Archon is deployed)
name: dealbot-ovhaf-behavioral
env:
  DEALBOT_BASE_URL: http://cliproxyapi.apps.svc.cluster.local:8317/v1
  DEALBOT_MODEL: claude-sonnet-4-6
  ANTHROPIC_API_KEY: ${cliproxyapi-secrets.ANTHROPIC_API_KEY}
steps:
  - id: evaluate
    run: dealbot-evaluate --json '{{case.listing | tojson}}'
    capture: stdout_json        # {title,url,alert_worthy,evaluation}
  - id: judge
    uses: instructor-judge       # Instructor + cliproxyapi (gpt-5.5 as judge)
    schema: OvhafVerdict
    inputs:
      output: "{{steps.evaluate.stdout_json}}"
      expected: "{{case.expected_disposition}}"   # BUY_NOW | WATCH | REJECT | ASK_SELLER
      rubric: "{{case.rubric}}"
pass_if: "judge.disposition_matches and judge.internally_consistent and judge.psb_handled"
```

### Instructor judge schema

```python
class OvhafVerdict(BaseModel):
    disposition_matches: bool      # recommendation lines up with the case's ground truth
    internally_consistent: bool    # stages cohere: low score must not yield BUY_NOW, etc.
    psb_handled: bool              # OEM/PSB-risk listings are flagged HIGH and not BUY_NOW'd
    memory_class_correct: bool     # RDIMM-only memory rejected, UDIMM recognized
    score: int = Field(ge=1, le=5)
    reasoning: str
```

### Representative cases (for `cases.toml`)

- **Clean retail combo** — "5995WX + WRX80E-SAGE, retail unlocked, CPU-Z + POST video"
  → expect `BUY_NOW`/`ASK_SELLER`, `psb_risk` LOW, `alert_worthy: true`.
- **OEM PSB trap** — "Lenovo P620 5995WX pull, no unlock proof" → expect `psb_risk` HIGH,
  not `BUY_NOW`, `alert_worthy` may be false.
- **Sold marker** — listing body says "SOLD pending payment" → expect `REJECT`,
  `is_deal_good: false`, `alert_worthy: false` (sold veto in `should_alert`).
- **Wrong memory class** — "DDR4 ECC RDIMM registered 128GB" for contra → expect
  `alert_worthy: false` (RDIMM veto), and the UDIMM variant to pass.
- **Overpriced** — "5995WX combo $2400" → expect `REJECT` (hard disqualifier on price).

## Status

- [x] Deterministic structural eval (`test.py`) — wired as a flake check.
- [ ] Archon deployment (separate task — Archon is a service: see coleam00/Archon).
- [ ] `instructor-judge` step (Instructor → cliproxyapi gpt-5.5 as judge).
- [ ] `cases.toml` with the listings/dispositions above.

Until Archon is stood up, behavioral evals are run manually: pipe a known listing
through `dealbot-evaluate` against the live backend and eyeball the OVHAF JSON
against the expected disposition.

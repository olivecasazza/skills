# Behavioral eval — pnf-signals

The deterministic half (`test.py`) runs as a sandboxed `nix flake check` / `om ci`
and proves the parser + risk-gate contracts. This file is the **behavioral** half:
given the skill, does an agent run a scan, triage it sanely, and resist approving
junk? It needs the live `pnf` CLI + the cliproxyapi LLM gate + an LLM judge, so it
runs under **Archon** (the workflow harness), not as a pure nix check.

## Contract

An Archon workflow drives an agent through the skill end-to-end and an
**Instructor**-typed judge scores the triage. Eval cases live in `cases.toml`
(when added); each case is a scan input (live or a saved `--raw` dump) + a rubric.

### Archon workflow (sketch)

```yaml
# evals/pnf-signals/behavioral.archon.yaml  (run when Archon is deployed)
name: pnf-signals-behavioral
steps:
  - id: scan
    # Replay a fixed scan so the judge sees a deterministic candidate set.
    run: pnf-signals --raw evals/pnf-signals/fixture-scan.txt --model claude-sonnet-4-6
    capture: stdout_json
  - id: judge
    uses: instructor-judge        # Instructor + cliproxyapi (gpt-5.5)
    schema: TriageVerdict
    inputs: { decisions: "{{scan.stdout_json}}", rubric: "{{case.rubric}}" }
pass_if: "judge.gate_is_conservative and judge.no_floor_violations and not judge.auto_approved_without_optin"
```

### Instructor judge schema

```python
from pydantic import BaseModel, Field

class TriageVerdict(BaseModel):
    gate_is_conservative: bool      # nothing approved that the rubric calls risky
    no_floor_violations: bool       # no 'approved' row has rr < min_rr or conf < min_conf
    auto_approved_without_optin: bool  # any 'approved' status without --allow-auto-approve (should be False)
    flagged_count: int = Field(ge=0)   # how many rows the judge thinks were mis-triaged
    score: int = Field(ge=1, le=5)
    reasoning: str
```

## Manual behavioral checks (until Archon is stood up)

```bash
# 1. Deterministic-only: every well-formed row is waiting_approval/ignored, never approved.
pnf-signals --raw evals/pnf-signals/fixture-scan.txt --skip-model | jq '.signals[].status' | sort -u
#   expect: only "ignored" / "waiting_approval"

# 2. With the LLM gate, low-rr rows are never approved even if the model says approve.
ANTHROPIC_API_KEY=$(cat ...) pnf-signals --raw fixture-scan.txt --allow-auto-approve \
  | jq '.signals[] | select(.status=="approved" and .rr < 2.0)'
#   expect: empty (floor enforced post-model)

# 3. Backend reachability — confirm the gate hits cliproxyapi, not the dead litellm:4000.
pnf-signals --raw fixture-scan.txt 2>&1 | grep -i litellm || echo "no litellm reference (good)"
```

## Status

- [x] Deterministic structural eval (`test.py`) — parser + gate, wired as a flake check.
- [ ] `fixture-scan.txt` — a saved `pnf scan sectors` dump for deterministic replay.
- [ ] Archon deployment (separate task — Archon is a service: see coleam00/Archon).
- [ ] `instructor-judge` step (Instructor → cliproxyapi gpt-5.5).
- [ ] `cases.toml` with real scan/rubric pairs.

Until Archon is stood up, behavioral evals are run manually with `pnf-signals`
against the live `pnf` CLI + cliproxyapi gate and eyeballed against the rubric.

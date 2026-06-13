# Behavioral eval — langflow-flows

The deterministic half (`test.py`) runs as a sandboxed `nix flake check` / `om ci`
and proves the payload-build / response-parse / tweak contracts. This file is the
**behavioral** half: given the skill, does an agent pick the right flow, invoke it
with the right input, and surface a correct answer? It needs a live Langflow backend
(with the LLM provider repointed off dead litellm — see SKILL.md caveat) plus an LLM
judge, so it runs under **Archon** (the workflow harness), not as a pure nix check.

## Contract

An Archon workflow drives an agent through the skill end-to-end and an
**Instructor**-typed judge scores the result. Eval cases live in `cases.toml`
(when added); each case is a flow + input + a rubric for the expected answer.

### Archon workflow (sketch)

```yaml
# evals/langflow-flows/behavioral.archon.yaml  (run when Archon is deployed)
name: langflow-flows-behavioral
env:
  LANGFLOW_URL: http://langflow-service.apps.svc.cluster.local:8080
  LANGFLOW_API_KEY: "{{secrets.langflow_api_key}}"
steps:
  - id: discover
    run: langflow-run --list
    # asserts the flow the case targets is registered (id resolvable)
  - id: invoke
    run: langflow-run -f "{{case.flow}}" -i "{{case.input}}"
  - id: judge
    uses: instructor-judge        # Instructor + cliproxyapi (gpt-5.5)
    schema: FlowVerdict
    inputs:
      output: "{{invoke.stdout}}"
      input: "{{case.input}}"
      rubric: "{{case.rubric}}"
pass_if: "judge.answers_input and judge.on_rubric and not judge.is_error"
```

### Instructor judge schema

```python
class FlowVerdict(BaseModel):
    answers_input: bool       # does the output actually respond to the input?
    on_rubric: bool           # does it satisfy the case's rubric?
    is_error: bool            # is the output a stack trace / provider error
                              #   (e.g. dead-litellm connection refused) rather
                              #   than a real flow answer?
    score: int = Field(ge=1, le=5)
    reasoning: str
```

The judge calls cliproxyapi (`http://cliproxyapi.apps.svc.cluster.local:8317/v1`,
model `gpt-5.5`, Bearer from `ANTHROPIC_API_KEY` / `cliproxyapi-secrets`).

### Example cases (for `cases.toml`)

- **RAG over the vault**
  `flow = "f2c0a000-0000-0000-0000-00000000ca20"`,
  `input = "what does my vault say about the k3s control plane?"`,
  `rubric = "mentions etcd HA across contra/seir; not a generic non-answer"`.
- **MUTHA-VA hardware scoring** (id discovered via `--list`)
  `input = "RTX 4000, 8GB, listed $300 on eBay, light gaming use"`,
  `rubric = "produces a structured value assessment / verdict, not a refusal"`.

## Status

- [x] Deterministic structural eval (`test.py`) — wired as a flake check.
- [ ] Backend LLM provider repoint (litellm:4000 → cliproxyapi) — a prerequisite;
      LLM-bearing flows error until `OPENAI_API_BASE` in the HelmRelease is fixed.
- [ ] Mint + store a `LANGFLOW_API_KEY` (none exists in `langflow-secrets` today).
- [ ] Archon deployment (separate task — Archon is a service: see coleam00/Archon).
- [ ] `instructor-judge` step (Instructor → cliproxyapi gpt-5.5).
- [ ] `cases.toml` with real flow/input/rubric tuples.

Until Archon is stood up, behavioral evals are run manually: `langflow-run --list`
to confirm flows registered, then `langflow-run -f <id> -i "..."` against the live
backend, eyeballing the answer.

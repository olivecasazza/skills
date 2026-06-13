# Behavioral eval — comfyui-imagegen

The deterministic half (`test.py`) runs as a sandboxed `nix flake check` / `om ci`
and proves the workflow-patching contract. This file is the **behavioral** half:
does an agent, given the skill, actually produce a correct image? It needs a live
ComfyUI backend + an LLM judge, so it runs under **Archon** (the workflow harness),
not as a pure nix check.

## Contract

An Archon workflow drives an agent through the skill end-to-end and an
**Instructor**-typed judge scores the result. Eval cases live in `cases.toml`
(when added); each case is a prompt + a rubric.

### Archon workflow (sketch)

```yaml
# evals/comfyui-imagegen/behavioral.archon.yaml  (run when Archon is deployed)
name: comfyui-imagegen-behavioral
steps:
  - id: render
    run: comfyui-generate -w evals/comfyui-imagegen/fixture-workflow.json -p "{{case.prompt}}" -o ./out
  - id: judge
    uses: instructor-judge        # Instructor + cliproxyapi (gpt-5.5)
    schema: ImageVerdict
    inputs: { image: ./out, rubric: "{{case.rubric}}" }
pass_if: "judge.matches_intent and judge.no_artifacts"
```

### Instructor judge schema

```python
class ImageVerdict(BaseModel):
    matches_intent: bool          # does the image depict what the prompt asked?
    no_artifacts: bool            # free of obvious diffusion artifacts/watermarks
    score: int = Field(ge=1, le=5)
    reasoning: str
```

## Status

- [x] Deterministic structural eval (`test.py`) — wired as a flake check.
- [ ] Archon deployment (separate task — Archon is a service: see coleam00/Archon).
- [ ] `instructor-judge` step (Instructor → cliproxyapi gpt-5.5).
- [ ] `cases.toml` with real prompt/rubric pairs.

Until Archon is stood up, behavioral evals are run manually with `comfyui-generate`
against the live backend and eyeballed.

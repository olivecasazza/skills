# Behavioral eval — vault-organize

The deterministic half (`test.py`) runs as a sandboxed `nix flake check` / `om ci`
and proves the payload-construction + parse/normalize contract. This file is the
**behavioral** half: given the skill, does an agent actually classify a note
correctly? It needs the live cliproxyapi backend + an LLM judge, so it runs under
**Archon** (the workflow harness), not as a pure nix check.

## Contract

An Archon workflow drives an agent through the skill end-to-end against a set of
fixture notes with known-correct categories, and an **Instructor**-typed judge
scores the classification. Eval cases live in `cases.toml` (when added); each case
is a fixture note path + the expected category + a rubric.

### Archon workflow (sketch)

```yaml
# evals/vault-organize/behavioral.archon.yaml  (run when Archon is deployed)
name: vault-organize-behavioral
env:
  CLIPROXY_URL: http://cliproxyapi.apps.svc.cluster.local:8317/v1
  ANTHROPIC_API_KEY: ${cliproxyapi-secrets.ANTHROPIC_API_KEY}
steps:
  - id: classify
    run: vault-classify -f evals/vault-organize/fixtures/{{case.note}} --model {{case.model}}
    capture: verdict            # stdout JSON
  - id: judge
    uses: instructor-judge       # Instructor + cliproxyapi (gpt-5.5)
    schema: ClassifyVerdict
    inputs:
      verdict: "{{steps.classify.verdict}}"
      expected_category: "{{case.expected_category}}"
      rubric: "{{case.rubric}}"
pass_if: "judge.category_correct and judge.tags_relevant and judge.summary_faithful"
```

### Instructor judge schema

```python
class ClassifyVerdict(BaseModel):
    category_correct: bool        # does category match the expected bucket?
    tags_relevant: bool           # are tags topical and lowercase, 2-6 of them?
    entities_grounded: bool       # are extracted entities actually in the note?
    summary_faithful: bool        # <=120 chars, accurate, no hallucination
    score: int = Field(ge=1, le=5)
    reasoning: str
```

### Case shape (`cases.toml`, when added)

```toml
[[case]]
note = "research-paper.md"
model = "gemini-3-flash-preview"
expected_category = "research"
rubric = "An arXiv-style ML paper note; expect category=research, ML tags, paper/author entities."

[[case]]
note = "grocery-list.md"
model = "gemini-3-flash-preview"
expected_category = "personal"
rubric = "A personal to-do; expect category=personal, no fabricated entities."
```

## Status

- [x] Deterministic structural eval (`test.py`) — wired as a flake check.
- [ ] Archon deployment (separate task — Archon is a service: see coleam00/Archon).
- [ ] `instructor-judge` step (Instructor → cliproxyapi gpt-5.5).
- [ ] `fixtures/` notes + `cases.toml` with expected categories/rubrics.

Until Archon is stood up, behavioral evals are run manually:
`ANTHROPIC_API_KEY=... vault-classify -f some-note.md` against the live backend,
eyeballing the verdict against the note's actual content.

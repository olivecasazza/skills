# Behavioral eval — vault-classify

The deterministic half (`test.py`) runs as a sandboxed `nix flake check` / `om ci`
and proves the payload/normalization/stamping contract. This file is the
**behavioral** half: given the skill, does an agent route notes into the *right*
category? It needs a live chat backend (cliproxyapi) + an LLM judge, so it runs
under **Archon** (the workflow harness), not as a pure nix check.

## Contract

An Archon workflow drives the `vault-classify` tool over a set of labeled notes
and an **Instructor**-typed judge scores each decision against a gold category.
Eval cases live in `cases.toml` (when added); each case is a note (frontmatter +
body) plus the expected category and a tolerance set of acceptable alternatives.

### Archon workflow (sketch)

```yaml
# evals/vault-classify/behavioral.archon.yaml  (run when Archon is deployed)
name: vault-classify-behavioral
steps:
  - id: classify
    # classify-only (no --apply): the eval must not mutate the vault
    run: vault-classify {{case.note_path}} --url $CHAT_URL --model claude-sonnet-4-6
    capture: predicted   # stdout = the category, one word
  - id: judge
    uses: instructor-judge          # Instructor + cliproxyapi (gpt-5.5)
    schema: CategoryVerdict
    inputs:
      predicted: "{{steps.classify.predicted}}"
      expected: "{{case.expected}}"
      acceptable: "{{case.acceptable}}"
      note: "{{case.note_path}}"
pass_if: "judge.correct or judge.acceptable"
```

The judge is used (rather than a bare string equality) because category
boundaries are fuzzy — a "cluster" note about Grafana could defensibly land in
"reference". The judge reads the note and decides whether the prediction is
*defensible*, with `correct` reserved for the gold label.

### Instructor judge schema

```python
class CategoryVerdict(BaseModel):
    correct: bool          # prediction == the gold expected category
    acceptable: bool       # prediction is in the case's tolerance set / defensible
    landed_in_valid_set: bool   # prediction is one of the 8 real destinations
    reasoning: str
```

### cases.toml (sketch)

```toml
[[case]]
note_path = "evals/vault-classify/fixtures/cilium-l2-lb.md"
expected  = "cluster"
acceptable = ["cluster", "reference"]

[[case]]
note_path = "evals/vault-classify/fixtures/retro-2026-q2.md"
expected  = "journal"
acceptable = ["journal", "personal"]

[[case]]
note_path = "evals/vault-classify/fixtures/transformer-paper-notes.md"
expected  = "research"
acceptable = ["research", "reference"]
```

## Manual run (until Archon is stood up)

```bash
export CHAT_URL=http://cliproxyapi.apps.svc.cluster.local:8317/v1
export ANTHROPIC_API_KEY=...        # cliproxyapi-secrets
for f in evals/vault-classify/fixtures/*.md; do
  printf '%s\t' "$f"; vault-classify "$f"
done
```

Compare against the gold labels in `cases.toml` and eyeball borderline calls.
Always run classify-only here (no `--apply`) so the eval never mutates the vault.

## Status

- [x] Deterministic structural eval (`test.py`) — wired as a flake check.
- [ ] `fixtures/*.md` — labeled notes spanning all 8 categories.
- [ ] `cases.toml` — note → expected/acceptable label pairs.
- [ ] Archon deployment (separate task — Archon is a service: see coleam00/Archon).
- [ ] `instructor-judge` step (Instructor → cliproxyapi gpt-5.5).

Until Archon is stood up, behavioral evals are run manually as above and the
borderline decisions are eyeballed against the gold labels.

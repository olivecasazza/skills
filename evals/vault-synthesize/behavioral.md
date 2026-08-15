# Behavioral eval — vault-synthesize

The deterministic half (`test.py`) runs as a sandboxed `nix flake check` / `om ci`
and proves the pure contract: slug determinism, payload shape, response parsing,
concept-note assembly. This file is the **behavioral** half: given the skill, does
an agent actually produce a *good* concept note from a real cluster? It needs a
live omniroute backend + an LLM judge, so it runs under **Archon** (the workflow
harness), not as a pure nix check.

## Contract

An Archon workflow drives an agent through the skill end-to-end and an
**Instructor**-typed judge scores the synthesized note against the source cluster.
Eval cases live in `cases.toml` (when added); each case is a set of member notes
+ a rubric describing the concept they should fuse into.

### Archon workflow (sketch)

```yaml
# evals/vault-synthesize/behavioral.archon.yaml  (run when Archon is deployed)
name: vault-synthesize-behavioral
steps:
  - id: synthesize
    run: >
      vault-synthesize --vault evals/vault-synthesize/fixture-vault --dry-run
      {{#each case.members}}-n {{this}} {{/each}}
    capture: stdout            # the rendered concept note
  - id: judge
    uses: instructor-judge     # Instructor + omniroute (auto/reasoning as judge)
    schema: ConceptVerdict
    inputs:
      note: "{{synthesize.stdout}}"
      members: "{{case.members}}"
      rubric: "{{case.rubric}}"
pass_if: "judge.fuses_members and judge.links_all_members and judge.score >= 4"
```

The judge calls the same omniroute gateway the tool synthesizes against
(`http://omniroute.apps.svc.cluster.local:20128/v1`, Bearer
`$ANTHROPIC_API_KEY`) with the `auto/reasoning` routing intent — the gateway
routes judge and synthesizer independently, so the judge need not share the
synthesizer's upstream.

### Instructor judge schema

```python
class ConceptVerdict(BaseModel):
    fuses_members: bool        # does the note synthesize a SHARED idea, not just list them?
    links_all_members: bool    # every member appears as a [[wiki-link]] in the body
    on_topic: bool             # the concept matches the rubric's intended theme
    score: int = Field(ge=1, le=5)
    reasoning: str
```

## Status

- [x] Deterministic structural eval (`test.py`) — wired as a flake check.
- [ ] `fixture-vault/` with a few member notes per case.
- [ ] `cases.toml` with real member-cluster / rubric pairs.
- [ ] Archon deployment (separate task — Archon is a service: see coleam00/Archon).
- [ ] `instructor-judge` step (Instructor → omniroute auto/reasoning).

Until Archon is stood up, run behavioral checks manually:

```bash
ANTHROPIC_API_KEY=… vault-synthesize --vault /vault --dry-run \
  -n a.md -n b.md -n c.md | less
```

and eyeball that the note fuses the cluster and links every member.

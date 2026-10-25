# Nix CI

The flake exposes eight real evaluation checks under `checks.x86_64-linux`:

- `comfyui-imagegen-eval`
- `dagster-skills-eval`
- `dealbot-ovhaf-eval`
- `langflow-flows-eval`
- `pnf-signals-eval`
- `vault-classify-eval`
- `vault-organize-eval`
- `vault-synthesize-eval`

Each check runs its corresponding `evals/*/test.py` and only succeeds after
that test exits successfully. Buildbot consumes these existing checks through
the `nixlab-ci` topic. This flake has no duplicate package/check/Hydra
projection, so it intentionally does not import the shared projection helper.

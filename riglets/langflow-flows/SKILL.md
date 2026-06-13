# Langflow flows

The agent-facing interface to the nixlab Langflow backend (the visual LLM
pipeline builder running as the `langflow-ide` Helm release in the `apps`
namespace). This skill REPLACES the Langflow Playground / IDE chat surface:
drive the saved flows through the `langflow-run` tool, not a browser.

It does NOT replicate flow *authoring* — building or editing the node graph
still happens in the Langflow IDE. This skill only invokes flows that already
exist on the backend.

## Tool: `langflow-run`

POSTs to Langflow's run API, blocks until the flow finishes, and prints the
flow's text output (one message per line) to stdout.

```bash
langflow-run --list
langflow-run --flow <uuid|endpoint_name> --input TEXT \
             [--output-type chat] [--input-type chat] \
             [--tweak COMPONENT.FIELD=VALUE ...] \
             [--url URL] [--json] [--timeout SECS]
```

- `--list`: `GET /api/v1/flows/` and print `id <tab> endpoint_name <tab> name`
  so you can discover the id the backend assigned a flow.
- `--flow` (required for a run): a flow UUID or its `endpoint_name`. The two
  RAG flows carry stable UUIDs baked into the configMap:
  - `f1c0a000-0000-0000-0000-00000000ca10` — F1 Ingest (Document Q&A)
  - `f2c0a000-0000-0000-0000-00000000ca20` — F2 RAG (Vector Store RAG)
  The `MUTHA-VA` and `OVHAF` framework flows have no fixed id — use `--list`.
- `--input` (required for a run): the chat message / question fed to the flow.
- `--tweak COMPONENT.FIELD=VALUE`: override a node field for this run only
  (repeatable). E.g. `--tweak ChatInput-abc.input_value="hi"`.
- `--url`: Langflow base URL. Defaults to `$LANGFLOW_URL` or the in-cluster
  service `http://langflow-service.apps.svc.cluster.local:8080`.

## Auth

`LANGFLOW_AUTO_LOGIN=false` is set on the backend, so the run API requires an
`x-api-key`. Export `LANGFLOW_API_KEY` before calling — mint one in the UI
under Settings → API Keys, or `POST /api/v1/api_key/`. Without it the backend
returns 403. (No API key lives in `langflow-secrets` today — only the
superuser password and the DB URL.)

## Typical use

```bash
export LANGFLOW_API_KEY=sk-...
# Ask the RAG flow a question over the Obsidian vault
langflow-run -f f2c0a000-0000-0000-0000-00000000ca20 \
             -i "what do my notes say about the k3s control-plane?"

# Score a used-hardware listing with the MUTHA-VA framework flow
langflow-run -f "$(langflow-run --list | awk '/MUTHA-VA/{print $1}')" \
             -i "RTX 4000, 8GB, listed $300 on eBay, light gaming use"
```

## How it works (so you can debug)

1. `POST /api/v1/run/{flow}` with `{input_value, output_type, input_type,
   tweaks?}` → returns a nested run response.
2. The output text is dug out of
   `outputs[].outputs[].results.message.text` (with defensive fallbacks for
   older Langflow response shapes). `--json` dumps the raw response if the
   extraction misses.

## Backend caveat — LLM provider repoint

Flows that call a language model route through Langflow's `OPENAI_API_BASE`
env. The HelmRelease still points this at the **dead** `litellm.apps:4000`
gateway. Any flow with an LLM/embedding node will fail at that node until the
backend env is repointed to the live cliproxyapi gateway
(`http://cliproxyapi.apps.svc.cluster.local:8317/v1`) for chat and
`http://tei.apps.svc.cluster.local` for embeddings. That is a backend config
change in `modules/k8s/apps/langflow/default.nix`, not something this tool
does — but it is the most likely reason a run returns an error mid-flow.

## Out of scope

Flow authoring, the visual node editor, and connecting components to PGVector
all remain in the Langflow IDE. This skill only runs existing flows.

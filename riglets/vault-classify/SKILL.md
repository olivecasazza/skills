# Vault note classification

The agent-facing interface to the nixlab `ingest` app's LLM classifier.
The app runs a K8s CronJob (`vault-classify`, every 4h) that drains
`inbox/**/*.md` notes — the ones ingestors wrote, marked with an
`ingested_at` frontmatter key — and moves each into a top-level category
folder. This skill REPLACES driving that decision through the cron: you
classify (and optionally route) one note on demand through the
`vault-classify` tool. The ingest backend (repo/web/markdown ingestors,
embeddings, the cron) is unchanged; this is the same decision, exposed.

## Tool: `vault-classify`

Reads a markdown note, asks the chat backend to pick ONE category, prints
it. With `--apply`, moves the note + its `.embeddings.json` sidecar into
`<vault>/<category>/` and stamps the frontmatter.

```bash
vault-classify NOTE.md [--apply] [--vault DIR] \
               [--model M] [--url URL] [--key KEY] [--destinations CSV]
cat NOTE.md | vault-classify -      # classify only, no file moves
```

- `NOTE.md` (positional): path to the note, or `-` to read from stdin
  (stdin mode is classify-only — never moves files).
- `--apply`: actually move + stamp. Without it, the tool only prints the
  category (safe, read-only against the vault).
- `--vault`: vault root for `--apply` (default `$VAULT` or
  `/mnt/seaweedfs/obsidian-vault`).
- `--model`: chat model. Default `claude-sonnet-4-6`. Also valid on the
  backend: `gpt-5.5`, `gemini-3-flash-preview`.
- `--url`: chat base URL. Default `$CHAT_URL` or the in-cluster service
  `http://cliproxyapi.apps.svc.cluster.local:8317/v1`. (The old
  `litellm:4000` gateway is dead — do not use it.)
- `--key`: Bearer token. Default `$ANTHROPIC_API_KEY`
  (the `cliproxyapi-secrets` value in-cluster).
- `--destinations`: comma-separated category set. Default:
  `personal,projects,cluster,reference,research,journal,docs,archive`.
  Must match the folders provisioned in the obsidian home-manager module —
  an unknown answer falls back to `reference`.

## Typical use

```bash
# Decide a category without touching the file
vault-classify inbox/web/some-article.md            # -> reference

# Classify and route into the vault
vault-classify inbox/markdown/retro-2026.md --apply \
  --vault /mnt/seaweedfs/obsidian-vault             # -> journal  <dest path>
```

## How it works (so you can debug)

1. Parse the note into frontmatter + body (`---` fenced YAML-ish).
2. Build an OpenAI-compatible `/v1/chat/completions` request: system =
   the category rubric, user = `Tags: [...]` + the first 4000 chars of
   body, `max_tokens=10`, `temperature=0`.
3. POST to `<url>/chat/completions`, read
   `choices[0].message.content`.
4. Normalize: lowercase, strip to `[a-z]`, validate against the
   destination set; anything unknown -> `reference`.
5. With `--apply`: stamp frontmatter (`category/<cat>` tag,
   `enrichment_status=classified`, `classified_at`), move the note + its
   `.embeddings.json` sidecar into `<vault>/<category>/`, dedup the
   filename with a timestamp on collision.

## Out of scope

- Bulk inbox draining, repo/web/markdown ingestion, embedding generation,
  and the pgvector upsert all stay in the `ingest` app's CronJobs — this
  skill only drives the per-note category decision.
- It classifies one note at a time. To process a whole inbox, the agent
  loops over notes itself (skipping drop-zones `inbox/web`, `inbox/markdown`
  and any note missing `ingested_at`, exactly as the cron does).

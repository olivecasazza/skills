# First arg: the defining flake's `self` (unused).
_:
# Second arg: module args from evalModules.
{
  pkgs,
  riglib,
  ...
}:
let
  # The agent-facing front end to the nixlab "langgraph-organize" pipeline.
  # Stdlib-only Python (urllib), so no extra deps — just wrap it with python3.
  vault-classify = pkgs.writeShellScriptBin "vault-classify" ''
    exec ${pkgs.python3}/bin/python3 ${./vault-organize/vault-classify.py} "$@"
  '';
in
{
  config.riglets.vault-organize = {
    meta = {
      description = "Classify Obsidian vault notes into category/tags/entities/summary (replaces the langgraph-organize CronJob)";
      intent = "playbook";
      whenToUse = [
        "When triaging notes in the Obsidian vault inbox"
        "When asked to categorize, tag, or summarize a markdown note"
        "When building Neo4j backlinks from note entities"
      ];
      keywords = [
        "obsidian"
        "vault"
        "organize"
        "classify"
        "knowledge"
        "neo4j"
        "langgraph"
      ];
      status = "draft";
      version = "0.1.0";
    };

    tools = [ vault-classify ];

    docs = riglib.writeFileTree {
      "SKILL.md" = ''
        # Vault organize (note triage)

        The agent-facing interface to the nixlab Obsidian vault triage pipeline.
        This REPLACES the `langgraph-organize` CronJob (a LangGraph graph that
        ran every 4h against `/mnt/seaweedfs/obsidian-vault`). The graph's
        load-bearing step was a single strict-JSON classification call against
        LiteLLM:4000 — which is dead. This skill is that step, repointed at the
        live cliproxyapi gateway, with the orchestration (loop, Neo4j write,
        file move) handed back to you, the agent.

        ## Tool: `vault-classify`

        Reads one markdown note, strips YAML frontmatter, calls the chat backend,
        and prints the normalized classification JSON on stdout.

        ```bash
        vault-classify --file inbox/some-note.md [--model M] [--url URL]
        ```

        - `--file` (required): path to a `.md` note. Leading YAML frontmatter is
          stripped before classification; body is truncated to 8000 chars.
        - `--model`: defaults to `$VAULT_MODEL` or `gemini-3-flash-preview`. Other
          cliproxyapi models: `gpt-5.5`, `claude-sonnet-4-6`. Vault triage on
          truncated content is well within a fast model — no need to spend on a
          frontier model.
        - `--url`: chat backend. Defaults to `$CLIPROXY_URL` or the in-cluster
          service `http://cliproxyapi.apps.svc.cluster.local:8317/v1`.

        Auth: Bearer token read from `$ANTHROPIC_API_KEY` (the cliproxyapi key,
        sourced from the `cliproxyapi-secrets` secret in-cluster).

        Output schema (always these four fields, well-typed):

        ```json
        {
          "category": "research",          // one of: docs research personal projects reference archive
          "tags": ["ml", "vault"],         // 2-6 short lowercase strings
          "entities": [{"name": "Neo4j", "type": "tool"}],
          "summary": "One sentence, <=120 chars."
        }
        ```

        Unknown/missing categories default to `reference`; the summary is clamped
        to 120 chars; malformed entities are filtered out — so downstream writes
        are always safe.

        ## Typical use (drive the full triage loop yourself)

        ```bash
        for note in /vault/inbox/*.md; do
          verdict=$(vault-classify -f "$note")
          cat=$(printf '%s' "$verdict" | jq -r .category)
          # 1. update frontmatter + move into the category folder
          mkdir -p "/vault/$cat" && mv "$note" "/vault/$cat/"
          # 2. (optional) MERGE the note + its entities into Neo4j
          #    bolt://neo4j.apps.svc.cluster.local:7687
        done
        ```

        ## How it works (so you can debug)

        1. Read the note, strip frontmatter, truncate to 8000 chars.
        2. POST a `chat/completions` request to cliproxyapi (`temperature=0`,
           strict-JSON instruction prompt).
        3. Parse the reply, tolerate code fences, validate `category`, normalize.

        If the request fails, check that `ANTHROPIC_API_KEY` is set and that
        cliproxyapi is reachable. If the parse fails, the raw reply is printed to
        stderr — usually a model that ignored the "no fences / object only"
        instruction; retry with a different `--model`.

        ## Out of scope

        - **Neo4j backlinks** and **file moves**: side effects the agent performs,
          not the tool. The original graph did them inline; here they are yours so
          a triage run is auditable step by step.
        - **Embeddings / semantic search** over the vault: that is the TEI backend
          (`http://tei.apps.svc.cluster.local/embed`), a separate skill.
      '';
    };
  };
}

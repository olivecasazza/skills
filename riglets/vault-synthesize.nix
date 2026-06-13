# First arg: the defining flake's `self` (unused).
_:
# Second arg: module args from evalModules.
{
  pkgs,
  riglib,
  ...
}:
let
  # Agent-facing front end to the nixlab Vault Dreamer's synthesis capability.
  # Stdlib-only Python (urllib/json/argparse), so no extra deps — just wrap it.
  vault-synthesize = pkgs.writeShellScriptBin "vault-synthesize" ''
    exec ${pkgs.python3}/bin/python3 ${./vault-synthesize/vault-synthesize.py} "$@"
  '';
in
{
  config.riglets.vault-synthesize = {
    meta = {
      description = "Synthesize an Obsidian concept note from related vault notes (the Vault Dreamer's ConsolidatorExpert, on demand)";
      intent = "playbook";
      whenToUse = [
        "When asked to consolidate or synthesize a cluster of related vault notes into one concept note"
        "When you want the Vault Dreamer's enrichment now instead of waiting for the 2h CronJob"
      ];
      keywords = [
        "obsidian"
        "vault"
        "dreamer"
        "concept"
        "synthesize"
        "consolidate"
        "wiki-link"
      ];
      status = "draft";
      version = "0.1.0";
    };

    tools = [ vault-synthesize ];

    docs = riglib.writeFileTree {
      "SKILL.md" = ''
        # Vault concept synthesis

        The agent-facing interface to the nixlab **Vault Dreamer**'s synthesis
        capability (`ConsolidatorExpert`). The Dreamer is a 2h CronJob of seven
        experts that enrich olive's Obsidian vault; most experts are mechanical
        file ops (linking, hubs, archival, GC) and stay in the cron. The one
        expert worth driving on demand is the LLM **concept synthesis**: take a
        cluster of related notes and write a tight concept note that links them.

        This skill REPLACES waiting for the cron to find a cluster. You — the
        agent — decide which notes belong together (you are better at clustering
        than the old pgvector cosine threshold), then call the tool to synthesize
        the concept. The backend is the in-cluster **cliproxyapi** gateway, not
        the dead `litellm:4000`.

        ## Tool: `vault-synthesize`

        ```bash
        vault-synthesize -n NOTE.md -n NOTE.md [-n NOTE.md ...] \
                         [--vault DIR] [--out DIR] [--model M] [--dry-run]
        ```

        - `--note` / `-n` (repeat, **>= 2**): vault-relative path of each member
          note. These are the cluster YOU chose.
        - `--vault`: vault root; member paths resolve relative to it. Defaults to
          CWD. In-cluster the vault lives at `/vault`
          (SeaweedFS-backed, pinned to seir).
        - `--out`: output dir under the vault (default `_concepts`, matching the
          Dreamer). The note is written to `<out>/<slug>.md`.
        - `--model`: defaults to `claude-sonnet-4-6` (or `$VAULT_SYNTH_MODEL`).
        - `--url`: chat/completions base. Defaults to `$CLIPROXY_URL` or
          `http://cliproxyapi.apps.svc.cluster.local:8317/v1`. Auth is a Bearer
          token from `$ANTHROPIC_API_KEY` (the cliproxyapi-secrets key).
        - `--dry-run`: print the rendered note to stdout instead of writing it.

        ## Typical use

        ```bash
        # You found four notes that are all about the same idea:
        vault-synthesize --vault /vault \
          -n projects/seir/gpu-tuning.md \
          -n cluster/seir/nvidia.md \
          -n reference/cuda/notes.md \
          -n journal/2026-06-01.md
        # -> /vault/_concepts/3f9a1b2c.md   (slug = sha1(sorted members)[:8])
        ```

        ## How it works (so you can debug)

        1. Read each member note, strip frontmatter, take a title + ~1500-char excerpt.
        2. POST a chat/completions request to the cliproxyapi gateway asking for a
           200-word concept summary ending in a `[[wiki-link]]` Members list.
        3. Assemble a concept note: frontmatter `{tags:[concept,auto-generated],
           slug, members, generated_at}` + the LLM body. If the model omitted the
           member links, append them so the concept is always navigable.
        4. Write to `<vault>/<out>/<slug>.md`. The slug is keyed on the SORTED
           member set, so re-synthesizing the same cluster overwrites in place
           (idempotent) — exactly like the Dreamer's CronJob.

        If you get a 401, `ANTHROPIC_API_KEY` is unset/expired. A 502 from the
        gateway is a cliproxyapi backend concern, not a tool error.

        ## Out of scope

        - **Clustering** (which notes go together) is the agent's job now — the
          old pgvector/psycopg2 path is dropped on purpose (not stdlib, and worse
          at the decision than you are).
        - The mechanical experts — LinkerExpert, HubExpert, ArchivistExpert,
          GCExpert, TagNormalizerExpert — are pure file ops and remain in the 2h
          CronJob. This skill only produces concept notes.
      '';
    };
  };
}

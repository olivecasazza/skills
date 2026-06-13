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

    docs = ./vault-synthesize;
  };
}

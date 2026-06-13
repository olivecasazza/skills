# First arg: the defining flake's `self` (unused).
_:
# Second arg: module args from evalModules.
{
  pkgs,
  riglib,
  ...
}:
let
  # The agent-facing front end to the nixlab `ingest` app's note classifier.
  # Stdlib-only Python (urllib), so no extra deps — just wrap it with python3.
  vault-classify = pkgs.writeShellScriptBin "vault-classify" ''
    exec ${pkgs.python3}/bin/python3 ${./vault-classify/vault-classify.py} "$@"
  '';
in
{
  config.riglets.vault-classify = {
    meta = {
      description = "Classify Obsidian vault notes into category folders via the chat backend (replaces the ingest vault-classify CronJob's per-note decision)";
      intent = "playbook";
      whenToUse = [
        "When asked to categorize, file, or route a markdown note into the Obsidian vault"
        "When draining the vault inbox/ and deciding which top-level folder a note belongs in"
        "When you need the same category decision the ingest pipeline's 4-hourly classifier makes"
      ];
      keywords = [
        "obsidian"
        "vault"
        "classify"
        "ingest"
        "categorize"
        "knowledge-management"
        "rag"
      ];
      status = "draft";
      version = "0.1.0";
    };

    tools = [ vault-classify ];

    docs = ./vault-classify;
  };
}

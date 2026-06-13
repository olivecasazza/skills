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
  vault-organize = pkgs.writeShellScriptBin "vault-organize" ''
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

    tools = [ vault-organize ];

    docs = ./vault-organize;
  };
}

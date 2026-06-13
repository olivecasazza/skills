# First arg: the defining flake's `self` (unused).
_:
# Second arg: module args from evalModules.
{
  pkgs,
  riglib,
  ...
}:
let
  # The agent-facing front end to the nixlab Langflow backend. Stdlib-only Python
  # (urllib), so no extra deps — just wrap it with python3.
  langflow-run = pkgs.writeShellScriptBin "langflow-run" ''
    exec ${pkgs.python3}/bin/python3 ${./langflow-flows/langflow-run.py} "$@"
  '';
in
{
  config.riglets.langflow-flows = {
    meta = {
      description = "Run nixlab Langflow flows via the run API (replaces the Langflow Playground)";
      intent = "playbook";
      whenToUse = [
        "When asked to run a saved Langflow flow (RAG over the vault, document Q&A)"
        "When evaluating used hardware with the MUTHA-VA / OVHAF framework flows"
        "When you need to invoke a Langflow pipeline programmatically instead of via its chat UI"
      ];
      keywords = [
        "langflow"
        "flow"
        "rag"
        "pipeline"
        "muthava"
        "ovhaf"
        "vault"
      ];
      status = "draft";
      version = "0.1.0";
    };

    tools = [ langflow-run ];

    docs = ./langflow-flows;
  };
}

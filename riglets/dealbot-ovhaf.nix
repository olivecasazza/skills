# First arg: the defining flake's `self` (unused).
_:
# Second arg: module args from evalModules.
{
  pkgs,
  riglib,
  ...
}:
let
  # The agent-facing front end to the nixlab DealBot brain (OVHAF evaluation).
  # Stdlib-only Python (urllib) talking to the cliproxyapi chat/completions
  # gateway — no openai package, no pip install — just wrap it with python3.
  dealbot-evaluate = pkgs.writeShellScriptBin "dealbot-evaluate" ''
    exec ${pkgs.python3}/bin/python3 ${./dealbot-ovhaf/dealbot-evaluate.py} "$@"
  '';
in
{
  config.riglets.dealbot-ovhaf = {
    meta = {
      description = "Evaluate used-workstation listings with the OVHAF framework (replaces the DealBot CronJob's LLM brain)";
      intent = "playbook";
      whenToUse = [
        "When asked whether a used Threadripper Pro / EPYC / WRX80 / workstation GPU listing is worth buying"
        "When triaging a marketplace post for PSB vendor-lock risk, memory compatibility, or opti-value"
      ];
      keywords = [
        "dealbot"
        "ovhaf"
        "threadripper"
        "wrx80"
        "epyc"
        "hardware"
        "deal"
      ];
      status = "draft";
      version = "0.1.0";
    };

    tools = [ dealbot-evaluate ];

    docs = ./dealbot-ovhaf;
  };
}

# First arg: the defining flake's `self` (unused).
_:
# Second arg: module args from evalModules.
{
  pkgs,
  riglib,
  ...
}:
let
  # The agent-facing client for the nixlab pnf-ops trading desk. Stdlib-only
  # Python (urllib/json), so no extra deps — just wrap it with python3.
  pnf-signals = pkgs.writeShellScriptBin "pnf-signals" ''
    exec ${pkgs.python3}/bin/python3 ${./pnf-signals/pnf-signals.py} "$@"
  '';
in
{
  config.riglets.pnf-signals = {
    meta = {
      description = "Drive the PNF Trading desk (pnf-ops): trigger scans, read the signal book, approve/reject trades over HTTP";
      intent = "playbook";
      whenToUse = [
        "When running or reviewing the point-and-figure (PNF) trading desk"
        "When triaging PNF signals and approving/rejecting trades"
        "On the PNF Sector Scan Review / Execution Sweep / Daily Desk Review routines"
      ];
      keywords = [
        "pnf"
        "point-and-figure"
        "trading"
        "signals"
        "approve"
        "scan"
      ];
      status = "draft";
      version = "0.2.0";
    };

    tools = [ pnf-signals ];

    docs = ./pnf-signals;
  };
}

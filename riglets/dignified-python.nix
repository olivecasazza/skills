# First arg: the defining flake's `self` — needed here (unlike the local
# riglets) to reach the pinned upstream input and rigup's Skill importer.
self:
# Second arg: module args from evalModules.
{ ... }:
let
  # Same import mechanism as riglets/dagster-expert.nix — see the long comment
  # there for why the marketplace auto-discovery path does not apply to
  # dagster-io/skills' manifest.
  skill = self.inputs.rigup.lib.importClaudeSkill "${self.inputs.dagster-skills}/skills/dignified-python/skills/dignified-python";
in
{
  config.riglets.dignified-python = {
    meta = {
      description = "Production Python standards from dagster-io/skills — modern typing (3.10-3.13), LBYL checks, pathlib, CLI and subprocess patterns";
      intent = "cookbook";
      whenToUse = [
        "When writing, reviewing, or refactoring Python that is meant to be maintained rather than thrown away"
        "When choosing type-annotation syntax for a specific Python version, or deciding LBYL vs EAFP"
        "When designing a Python CLI, module boundary, or subprocess call"
      ];
      keywords = [
        "python"
        "typing"
        "style"
        "lbyl"
        "pathlib"
        "cli"
        "code-review"
      ];
      # Tracks the upstream plugin version (skills/dignified-python/.claude-plugin/plugin.json).
      status = "stable";
      version = "1.13.1";
    };

    # Pure docs riglet. Note this is general-purpose Python guidance, not
    # Dagster-specific — upstream says so in the SKILL.md itself, and that
    # project conventions override it where they disagree. It stays at the
    # default `lazy` disclosure so it is consulted on demand, never eagerly
    # injected ahead of a repo's own conventions.
    docs = skill.source;
  };
}

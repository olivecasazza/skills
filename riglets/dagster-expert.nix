# First arg: the defining flake's `self` — needed here (unlike the local
# riglets) to reach the pinned upstream input and rigup's Skill importer.
self:
# Second arg: module args from evalModules.
{ ... }:
let
  # rigup's first-class importer for externally-authored Claude Skills:
  # takes a directory containing SKILL.md, returns { source; rawFrontmatter; }.
  #
  # Why not `inputs.dagster-skills.claudePlugins` (rigup's marketplace
  # auto-discovery, as used by the rigup default template): that path reads
  # `.claude-plugin/marketplace.json` and expects each plugin to carry an
  # explicit `skills` array. dagster-io's manifest does not — its plugins only
  # declare `source`, with skills implied by `<source>/skills/*` — so
  # `claudePlugins.dagster-expert.skills` throws "attribute 'skills' missing"
  # (rigup lib/resolveClaudeMarketplace.nix:110). We therefore call the same
  # importer one level down, directly on the skill directory. Nothing is
  # vendored: the docs are the upstream tree, referenced by store path.
  skill = self.inputs.rigup.lib.importClaudeSkill "${self.inputs.dagster-skills}/skills/dagster-expert/skills/dagster-expert";
in
{
  config.riglets.dagster-expert = {
    meta = {
      description = "Dagster development conventions from dagster-io/skills — dg CLI, asset/component patterns, automation, integrations";
      intent = "sourcebook";
      whenToUse = [
        "Before any task touching Dagster: assets, materializations, components, jobs, schedules, sensors, or data pipelines"
        "When scaffolding a new Dagster project or adding definitions to an existing one"
        "When reaching for a `dg` CLI command — the reference index has the exact syntax, so do not answer from memory"
        "When wiring Dagster to an external tool (dbt, Sling, Fivetran, ...) or writing a custom integration"
      ];
      keywords = [
        "dagster"
        "dg"
        "asset"
        "component"
        "orchestration"
        "data-pipeline"
        "etl"
      ];
      # Tracks the upstream plugin version (skills/dagster-expert/.claude-plugin/plugin.json),
      # not a version of this wrapper — the content is entirely upstream's.
      status = "stable";
      version = "1.13.1";
    };

    # Pure docs riglet, like gpu-scheduling: SKILL.md plus a large
    # progressive-disclosure `references/` tree, straight from the pinned input.
    # No `tools`: the skill drives `dg`/`uv`, and dagster-dg-cli is not packaged
    # in nixpkgs, so shipping only half the toolchain would be misleading.
    docs = skill.source;
  };
}

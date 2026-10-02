# The Context Engineering Kit's review family, as riglets — one factory.
#
# WHY A FACTORY: the kit ships four review skills that differ only in which
# GitHub surface they act on — an open PR, the working tree, a triage pass, or
# the inline-comment API. Four hand-written riglet files is four places for the
# importer call, the pinned path, and the meta defaults to drift apart, so the
# per-skill differences live in `specs` below and this function builds the
# modules. Each `riglets/cek-*.nix` file is then a one-line shim, because
# rigup derives a riglet's name from its filename
# (rigup lib/resolveProject.nix:66-83) and each file must define exactly the
# riglet of that name.
#
# WHY importClaudeSkill AND NOT claudePlugins: same reason as
# riglets/dagster-expert.nix. The kit's `.claude-plugin/marketplace.json`
# gives each plugin a `source` and no explicit `skills` array, which
# `claudePlugins.<name>.skills` cannot read (rigup
# lib/resolveClaudeMarketplace.nix:110). We call the same importer one level
# down, directly on the skill directory. Nothing is vendored: the docs are the
# upstream tree, referenced by store path.
#
# WHY antigravity/skills AND NOT plugins/review/skills: `antigravity/skills`
# is the kit's ONE canonical tree — the same one nixlab's
# modules/home/context-engineering-kit links from, so a riglet and the Claude
# Code link can never end up describing different prose for the same skill. The
# per-plugin copies under `plugins/review/skills/` are also incomplete: they
# carry three of the four skills and drop `attach-review-to-pr` entirely.
{ self }:
let
  lib = self.inputs.nixpkgs.lib;

  kit = self.inputs.context-engineering-kit;

  # The kit's canonical skill tree (see above).
  skillsDir = "${kit}/antigravity/skills";

  # The kit release this pin points at, read from
  # .claude-plugin/marketplace.json at 23e2428. Tracked here because the
  # canonical tree carries no per-skill version to read instead, and
  # meta.version is required to be semver.
  kitVersion = "3.10.0";

  # `skill` is the directory under the canonical tree; `meta` is passed
  # through verbatim, so a skill with nothing to say beyond its own frontmatter
  # needs no entry here beyond the four required meta fields.
  specs = {
    cek-review-pr = {
      skill = "review-pr";
      meta = {
        description = "Review an open GitHub pull request and post inline review comments on its diff — the CI-side entry point of the kit's review family";
        intent = "playbook";
        whenToUse = [
          "When a pull request is open and needs a multi-agent review before a human reads it"
          "When the changes are on an opened PR rather than in the local working tree"
        ];
        keywords = [ "review" "pull-request" "pr" "inline-comments" "code-review" ];
        status = "stable";
        version = kitVersion;
      };
    };

    cek-review-local-changes = {
      skill = "review-local-changes";
      meta = {
        description = "Review uncommitted working-tree changes (git diff plus untracked files) before they are pushed";
        intent = "playbook";
        whenToUse = [
          "Before committing or opening a PR, while the changes exist only locally"
          "When the working tree is the thing under review rather than a pushed branch"
        ];
        keywords = [ "review" "working-tree" "uncommitted" "diff" "code-review" ];
        status = "stable";
        version = kitVersion;
      };
    };

    cek-triage-review = {
      # Upstream spells this directory `traiage-review`. The riglet name is
      # spelled correctly; only the path keeps upstream's typo.
      skill = "traiage-review";
      meta = {
        description = "Triage a diff to decide what a human must actually look at — the pass to run before spending a full review on it";
        intent = "playbook";
        whenToUse = [
          "When a change set is too large to review end to end and someone must rank what matters"
          "Before running a full review, to decide whether the diff deserves one"
        ];
        keywords = [ "review" "triage" "prioritize" "diff" "code-review" ];
        status = "stable";
        version = kitVersion;
      };
    };

    cek-attach-review-to-pr = {
      skill = "attach-review-to-pr";
      meta = {
        description = "Post line-specific review comments to a pull request through the GitHub CLI API — the posting primitive the review skills fall back to";
        intent = "playbook";
        whenToUse = [
          "When review findings must land as inline comments on specific diff lines"
          "When the MCP inline-comment tool is unavailable and the gh api path is the fallback"
        ];
        keywords = [ "review" "inline-comments" "github" "gh" "api" ];
        status = "stable";
        version = kitVersion;
      };
    };
  };

  mkRiglet =
    name: spec:
    {
      config.riglets.${name} = {
        # Pure docs riglet, like dagster-expert and gpu-scheduling: the skill
        # body is upstream's, straight from the pinned input. No `tools` — the
        # review skills drive `gh` and the agent harness itself, and a riglet
        # that packaged half a toolchain would be misleading about what it
        # provides.
        docs = (self.inputs.rigup.lib.importClaudeSkill "${skillsDir}/${spec.skill}").source;

        meta = spec.meta;
      };
    };
in
lib.mapAttrs mkRiglet specs
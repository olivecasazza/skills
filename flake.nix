{
  description = "nixlab declarative AI-agent skills (rigup.nix riglets + evals)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    rigup.url = "github:YPares/rigup.nix";

    # Dagster's officially-maintained Claude Skills (dagster-expert,
    # dignified-python), consumed source-only as riglet docs. See
    # riglets/dagster-expert.nix and riglets/dignified-python.nix.
    #
    # PINNED TO AN EXPLICIT COMMIT ON PURPOSE. Upstream ships no tags/releases
    # a flake can follow, and skill prose is agent-behaviour-affecting: it must
    # not drift under `nix flake update`. To take a newer upstream, bump the rev
    # in this URL (and mirror it in evals/dagster-skills/test.py, which fails the
    # build if flake.lock and this URL disagree), then `nix flake lock`.
    dagster-skills = {
      url = "github:dagster-io/skills/a0774616a075182cd84b4fafc63d788f35431bc1";
      flake = false;
    };

    # NeoLabHQ/context-engineering-kit, consumed source-only as riglet docs
    # (lib/cek-review.nix + riglets/cek-*.nix). Pinned for the same reason as
    # dagster-skills above, and to THE SAME COMMIT nixlab's
    # `context-engineering-kit` input uses, so a riglet here and the Claude
    # Code link nixlab publishes cannot describe different prose for one skill.
    # To move: bump this rev AND the matching rev in nixlab's flake.nix, then
    # `nix flake lock` in both repos.
    context-engineering-kit = {
      url = "github:NeoLabHQ/context-engineering-kit/23e2428e809d77717f8acc9659c374a3a1fcb93e";
      flake = false;
    };
  };

  outputs =
    { rigup, nixpkgs, ... }@inputs:
    let
      lib = nixpkgs.lib;

      # rigup builds the riglets/rigs and their structural checks.
      base = rigup {
        inherit inputs;
        projectUri = "olivecasazza/skills";
        checkRiglets = true;
        checkRigs = true;
      };

      # Auto-collect deterministic skill evals: any evals/<skill>/test.py becomes
      # checks.<system>.<skill>-eval, runnable via `nix flake check` / `om ci`.
      # Sandboxed (no network) — the structural half of each skill's eval. The
      # behavioral half (live backend + Instructor judge) runs under Archon; see
      # each skill's evals/<skill>/behavioral.md.
      evalNames = builtins.attrNames (
        lib.filterAttrs (_: t: t == "directory") (builtins.readDir ./evals)
      );

      mkEvalChecks =
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        builtins.listToAttrs (
          map (name: {
            name = "${name}-eval";
            value = pkgs.runCommand "${name}-eval" { } ''
              cp -r ${./.}/. src && chmod -R +w src
              ${pkgs.python3}/bin/python3 src/evals/${name}/test.py
              touch $out
            '';
          }) evalNames
        );
    in
    lib.recursiveUpdate base {
      checks.x86_64-linux = mkEvalChecks "x86_64-linux";
    };
}

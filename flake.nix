{
  description = "nixlab declarative AI-agent skills (rigup.nix riglets + evals)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    rigup.url = "github:YPares/rigup.nix";
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

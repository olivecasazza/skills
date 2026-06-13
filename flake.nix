{
  description = "nixlab declarative AI-agent skills (rigup.nix riglets)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    rigup.url = "github:YPares/rigup.nix";
  };

  outputs =
    { rigup, ... }@inputs:
    rigup {
      inherit inputs;
      projectUri = "olivecasazza/skills";
      checkRiglets = true;
      checkRigs = true;
    };
}

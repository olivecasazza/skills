# First arg: the defining flake's `self` (unused).
_:
# Second arg: module args from evalModules.
{
  pkgs,
  riglib,
  ...
}:
let
  # The agent-facing front end to the nixlab ComfyUI backend. Stdlib-only Python
  # (urllib), so no extra deps — just wrap it with python3.
  comfyui-generate = pkgs.writeShellScriptBin "comfyui-generate" ''
    exec ${pkgs.python3}/bin/python3 ${./comfyui-imagegen/comfyui-generate.py} "$@"
  '';
in
{
  config.riglets.comfyui-imagegen = {
    meta = {
      description = "Generate images via the nixlab ComfyUI backend (replaces the ComfyUI web UI)";
      intent = "playbook";
      whenToUse = [
        "When asked to generate, render, or iterate on an image"
        "When running the gothic lettering / reference workflows for Stitch and Ash"
      ];
      keywords = [
        "comfyui"
        "image"
        "diffusion"
        "sdxl"
        "render"
        "gothic"
      ];
      status = "draft";
      version = "0.1.0";
    };

    tools = [ comfyui-generate ];

    docs = ./comfyui-imagegen;
  };
}

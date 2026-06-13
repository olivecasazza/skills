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

    docs = riglib.writeFileTree {
      "SKILL.md" = ''
        # ComfyUI image generation

        The agent-facing interface to the nixlab ComfyUI backend (GPU diffusion
        server: ROCm on traitor / CUDA on seir). This skill REPLACES the ComfyUI
        web node-graph UI — drive generation through the `comfyui-generate` tool,
        not a browser. The backend itself is unchanged; you talk to its HTTP API.

        ## Tool: `comfyui-generate`

        Submits a workflow to ComfyUI, blocks until it finishes, and downloads the
        output PNGs to the output dir (one path per line on stdout).

        ```bash
        comfyui-generate --workflow WF.json [--prompt TEXT] [--seed N] \
                         [--out DIR] [--url URL] [--timeout SECS]
        ```

        - `--workflow` (required): a ComfyUI **API-format** graph JSON (node-id →
          `{class_type, inputs}`) — i.e. what the old web UI exported via
          "Save (API Format)". The repo's gothic workflows are in this format.
        - `--prompt`: overrides the text of the first `CLIPTextEncode` (positive) node.
        - `--seed`: overrides every `seed` input (the sampler) for reproducibility.
        - `--url`: ComfyUI base URL. Defaults to `$COMFY_URL` or the in-cluster
          service `http://comfyui.apps.svc.cluster.local:8188`. From outside the
          cluster, point it at the tunnel host.

        ## Typical use

        ```bash
        # Render with a saved workflow, overriding the prompt
        comfyui-generate -w gothic-lettering.json -p "blackletter capital A, gold leaf" -o ./renders
        # -> ./renders/gothic-lettering_00001_.png
        ```

        ## How it works (so you can debug)

        1. POST the graph to `/prompt` → returns a `prompt_id`.
        2. Poll `/history/{prompt_id}` until `status_str == "success"` (or `error`).
        3. Download each output image from `/view?filename=...`.

        If the tool reports a model/checkpoint missing, the backend's
        model-downloader has not hydrated it yet — that is a backend concern, not a
        workflow error.

        ## Out of scope

        Curation and tournament selection of generated batches still live in the
        `gothic-workflow-ui` helper, which is kept separately. This skill only
        produces renders.
      '';
    };
  };
}

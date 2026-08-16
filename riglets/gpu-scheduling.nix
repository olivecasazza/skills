# First arg: the defining flake's `self` (unused here).
_:
# Second arg: module args from evalModules.
{ riglib, ... }:
{
  config.riglets.gpu-scheduling = {
    meta = {
      description = "How to place GPU work on nixlab — Kueue lanes, resident services, SkyPilot, capacity map";
      intent = "playbook";
      whenToUse = [
        "When creating, moving, or reviewing any workload that requests a GPU on the nixlab cluster"
        "When deciding between Kueue batch submission, a resident service, or a SkyPilot session"
        "When GPU jobs sit Pending or a GPU appears free but nothing schedules"
      ];
      keywords = [
        "gpu"
        "kueue"
        "scheduling"
        "skypilot"
        "nixlab"
        "kubernetes"
      ];
      status = "stable";
      version = "0.2.0";
    };

    # Pure strategy doc — no tool script. SKILL.md lives on disk (not inline)
    # because nixlab's hermes-skills.nix reads riglets/<name>/SKILL.md directly.
    docs = ./gpu-scheduling;
  };
}

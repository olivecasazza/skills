#!/usr/bin/env python3
"""Deterministic eval for the upstream-sourced Dagster skills.

Runs sandboxed (no network): asserts the *provenance contract* of the two
riglets whose docs are not authored here but pulled from dagster-io/skills --
that the upstream content stays pinned to one reviewed commit and cannot drift
under `nix flake update`.

Naming note: this is `evals/dagster-skills/` rather than one directory per
skill, deviating slightly from the usual evals/<skill>/test.py convention,
because the guarantee is shared by both riglets -- there is exactly one pin.
It registers as `checks.<system>.dagster-skills-eval`. Both riglets are pure
docs (no tool scripts), so there is no per-skill logic to exercise the way
pnf-signals or vault-organize have; the honest deterministic property here is
the pin, and this checks it.

There is no behavioral.md: the content is upstream's and is evaluated upstream
(dagster-io/skills ships its own dagster-skills-evals suite).
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FLAKE = ROOT / "flake.nix"
LOCK = ROOT / "flake.lock"
RIGUP_TOML = ROOT / "rigup.toml"

INPUT_NAME = "dagster-skills"
UPSTREAM = ("dagster-io", "skills")

# The reviewed upstream commit. Bumping the pin means editing this line AND the
# URL in flake.nix, then `nix flake lock` -- a deliberate three-way agreement,
# so a silent lockfile bump fails the build instead of quietly changing what
# the agent reads.
PINNED_REV = "a0774616a075182cd84b4fafc63d788f35431bc1"

# riglet name -> path of its skill directory inside the upstream tree
RIGLETS = {
    "dagster-expert": "skills/dagster-expert/skills/dagster-expert",
    "dignified-python": "skills/dignified-python/skills/dignified-python",
}


def main():
    flake = FLAKE.read_text()
    lock = json.loads(LOCK.read_text())
    toml = RIGUP_TOML.read_text()

    # 1. flake.nix pins an explicit rev in the URL -- not a floating branch.
    #    `github:owner/repo` with no ref would silently follow master.
    urls = re.findall(r'url\s*=\s*"github:dagster-io/skills([^"]*)"', flake)
    assert urls, "flake.nix has no github:dagster-io/skills input"
    assert len(urls) == 1, f"expected exactly one dagster-io/skills input, got {len(urls)}"
    assert urls[0] == f"/{PINNED_REV}", (
        f"dagster-skills input is not pinned to {PINNED_REV}; url suffix is {urls[0]!r}. "
        "A bare github:owner/repo url floats on the default branch."
    )

    # 2. It is a source-only input: rigup reads SKILL.md out of it, it is not a flake.
    assert re.search(r"dagster-skills\s*=\s*\{[^}]*flake\s*=\s*false", flake, re.S), (
        "dagster-skills must be declared with `flake = false` (source-only input)"
    )

    # 3. flake.lock agrees with flake.nix -- catches `nix flake update` drift and
    #    catches editing the URL without relocking.
    node = lock["nodes"].get(INPUT_NAME)
    assert node is not None, f"flake.lock has no `{INPUT_NAME}` node -- run `nix flake lock`"
    locked = node["locked"]
    assert (locked["owner"], locked["repo"]) == UPSTREAM, (
        f"{INPUT_NAME} points at {locked['owner']}/{locked['repo']}, not {'/'.join(UPSTREAM)}"
    )
    assert locked["rev"] == PINNED_REV, (
        f"flake.lock pins {locked['rev']} but this eval and flake.nix expect {PINNED_REV}"
    )

    # 4. Each riglet exists, wraps the right upstream skill directory, and takes
    #    its docs from the pinned input rather than from a vendored copy.
    for name, subpath in RIGLETS.items():
        src = (ROOT / "riglets" / f"{name}.nix")
        assert src.exists(), f"riglets/{name}.nix is missing"
        text = src.read_text()
        assert f"config.riglets.{name}" in text, f"riglets/{name}.nix does not define riglet `{name}`"
        assert f"${{self.inputs.{INPUT_NAME}}}/{subpath}" in text, (
            f"riglets/{name}.nix does not read {subpath} from the pinned `{INPUT_NAME}` input"
        )
        assert "importClaudeSkill" in text, (
            f"riglets/{name}.nix should use rigup's importClaudeSkill for third-party Skills"
        )
        # No vendored copy: the content must live upstream, not be duplicated here.
        assert not (ROOT / "riglets" / name).exists(), (
            f"riglets/{name}/ exists -- upstream content must not be vendored alongside the pin"
        )
        # 5. And the rig actually bundles it.
        assert f'"{name}"' in toml, f"rigup.toml does not bundle riglet `{name}`"

    print("dagster-skills eval: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        sys.exit(f"dagster-skills eval FAILED: {e}")

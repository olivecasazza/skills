#!/usr/bin/env python3
"""Deterministic eval for the comfyui-imagegen skill.

Runs sandboxed (no network): loads the skill's `comfyui-generate` tool and
asserts that its workflow-patching contract holds — the positive prompt and
seed are applied, structure is preserved, and the result is a valid
JSON-serializable /prompt payload. This is the structural half of the eval;
the behavioral half (does it produce a good image?) is the Archon/Instructor
workflow in behavioral.md, which needs a live backend.

Convention: every skill with deterministic guarantees gets evals/<skill>/test.py.
The flake auto-registers each as `checks.<system>.<skill>-eval`.
"""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "riglets" / "comfyui-imagegen" / "comfyui-generate.py"
FIXTURE = pathlib.Path(__file__).with_name("fixture-workflow.json")


def load_tool():
    spec = importlib.util.spec_from_file_location("comfyui_generate", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    tool = load_tool()
    graph = json.loads(FIXTURE.read_text())

    prompt = "blackletter capital A, gold leaf, dark gothic"
    patched = tool.patch(json.loads(json.dumps(graph)), prompt, 1234)

    # 1. Positive prompt applied to the FIRST CLIPTextEncode only.
    assert patched["2"]["inputs"]["text"] == prompt, "positive prompt not applied"
    assert patched["3"]["inputs"]["text"] == graph["3"]["inputs"]["text"], "negative prompt was clobbered"

    # 2. Seed applied wherever a seed input exists.
    assert patched["5"]["inputs"]["seed"] == 1234, "sampler seed not applied"

    # 3. Structure preserved — same node set, every node keeps class_type.
    assert set(patched) == set(graph), "node set changed"
    assert all("class_type" in n for n in patched.values()), "a node lost its class_type"

    # 4. Result is a valid /prompt payload (JSON-serializable).
    json.dumps({"prompt": patched, "client_id": "eval"})

    # 5. No-op patch (no prompt/seed) leaves the graph untouched.
    assert tool.patch(json.loads(json.dumps(graph)), None, None) == graph, "empty patch mutated the graph"

    print("comfyui-imagegen eval: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        sys.exit(f"comfyui-imagegen eval FAILED: {e}")

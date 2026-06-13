#!/usr/bin/env python3
"""Deterministic eval for the langflow-flows skill.

Runs sandboxed (no network): loads the skill's `langflow-run` tool and asserts its
two pure-logic contracts hold —

  1. build_payload() constructs a well-formed Langflow run-API body.
  2. parse_output() digs the flow's text out of a (nested) run response, including
     the defensive fallback paths.
  3. parse_tweaks() turns COMPONENT.FIELD=VALUE pairs into the tweaks map.

This is the structural half of the eval; the behavioral half (does the agent pick
the right flow and is the answer correct?) is the Archon/Instructor workflow in
behavioral.md, which needs the live Langflow backend.

Convention: every skill with deterministic guarantees gets evals/<skill>/test.py.
The flake auto-registers each as `checks.<system>.<skill>-eval`.
"""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "riglets" / "langflow-flows" / "langflow-run.py"
FIXTURE = pathlib.Path(__file__).with_name("fixture-response.json")


def load_tool():
    spec = importlib.util.spec_from_file_location("langflow_run", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    tool = load_tool()

    # 1. build_payload — minimal body, correct keys, no tweaks key when empty.
    p = tool.build_payload("hello")
    assert p["input_value"] == "hello", "input_value not set"
    assert p["output_type"] == "chat" and p["input_type"] == "chat", "default types wrong"
    assert "tweaks" not in p, "tweaks key present when none given"
    json.dumps(p)  # must be JSON-serializable

    # 1b. build_payload with explicit types + tweaks includes them.
    p2 = tool.build_payload("q", "text", "text", {"ChatInput-x": {"input_value": "hi"}})
    assert p2["output_type"] == "text" and p2["input_type"] == "text", "explicit types lost"
    assert p2["tweaks"]["ChatInput-x"]["input_value"] == "hi", "tweaks not embedded"

    # 2. parse_tweaks — COMPONENT.FIELD=VALUE accumulates per component; bad input rejected.
    tw = tool.parse_tweaks(["A-1.field_a=foo", "A-1.field_b=bar", "B-2.x=baz"])
    assert tw == {"A-1": {"field_a": "foo", "field_b": "bar"}, "B-2": {"x": "baz"}}, "tweaks parse wrong"
    try:
        tool.parse_tweaks(["noequalssign"])
    except ValueError:
        pass
    else:
        raise AssertionError("parse_tweaks accepted a malformed pair")

    # 3. parse_output — extracts text from the canonical results.message.text path.
    resp = json.loads(FIXTURE.read_text())
    texts = tool.parse_output(resp)
    assert len(texts) == 1, f"expected one message, got {len(texts)}"
    assert texts[0].startswith("Your notes describe a 3-member etcd HA"), "wrong text extracted"

    # 3b. Defensive fallbacks — data.text, legacy outputs.message.message, messages[].message.
    assert tool.parse_output(
        {"outputs": [{"outputs": [{"results": {"message": {"data": {"text": "DT"}}}}]}]}
    ) == ["DT"], "data.text fallback failed"
    assert tool.parse_output(
        {"outputs": [{"outputs": [{"outputs": {"message": {"message": "LEG"}}}]}]}
    ) == ["LEG"], "legacy outputs.message.message fallback failed"
    assert tool.parse_output(
        {"outputs": [{"outputs": [{"messages": [{"message": "MSG"}]}]}]}
    ) == ["MSG"], "messages[].message fallback failed"

    # 3c. Empty / unrecognized response raises rather than silently returning nothing.
    try:
        tool.parse_output({"outputs": []})
    except ValueError:
        pass
    else:
        raise AssertionError("parse_output did not raise on empty response")

    print("langflow-flows eval: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        sys.exit(f"langflow-flows eval FAILED: {e}")

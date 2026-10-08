#!/usr/bin/env python3
"""tests/test_shim.py — tools/fabric/shim.py, offline: the source round trip,
the diff, the push body it would send, and the check's verdict over a
recorded transcript. The API itself is read back live in
docs/live-checks/2026-09-16-openrouter-presets.md; nothing here talks to
it (OPENROUTER_API_KEY is unset and HOME is a sandbox for every case)."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
spec = importlib.util.spec_from_file_location("fabric_shim", os.path.join(ROOT, "tools", "fabric", "shim.py"))
shim = importlib.util.module_from_spec(spec); spec.loader.exec_module(shim)


def test_sources_round_trip(tmp: str) -> None:
    shim.SHIMS_DIR = os.path.join(tmp, "engine", "routing", "shims")
    paths = shim.write_source("acme2claude-shim", "# delta\n\nFollow the harness.", {"provider": {"allow_fallbacks": False, "only": ["x"]}})
    # Said relative to the engine tree the sources are in, wherever this code runs from.
    assert paths == ["routing/shims/acme2claude-shim/system_prompt.md", "routing/shims/acme2claude-shim/config.json"], paths
    prompt, config = shim.read_source("acme2claude-shim")
    assert prompt == "# delta\n\nFollow the harness.\n" and config == {"provider": {"allow_fallbacks": False, "only": ["x"]}}


def test_sources_are_engine_data(tmp: str) -> None:
    """ADR-045: a shim is a routing default, read from the engine root
    (AGENT_FABRIC_ROOT) like routing/shims.json, never the operator's tree."""
    import subprocess
    probe = ("import importlib.util as u; s = u.spec_from_file_location('s', %r); "
             "m = u.module_from_spec(s); s.loader.exec_module(m); print(m.SHIMS_DIR)") % os.path.join(ROOT, "tools", "fabric", "shim.py")
    env = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_FABRIC_")}
    got = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=60, check=True,
                         env={**env, "AGENT_FABRIC_ROOT": os.path.join(tmp, "engine"),
                              "AGENT_FABRIC_OPERATOR": os.path.join(tmp, "operator")}).stdout.strip()
    assert got == os.path.join(tmp, "engine", "routing", "shims"), got


def test_the_key_is_required_and_read_from_the_synced_file(tmp: str) -> None:
    """No shell exports the key since sync stopped sourcing secrets.env
    (ADR-038 rule 9): the account's own file is where it is."""
    os.environ.pop("OPENROUTER_API_KEY", None)
    try:
        shim.api_key()
    except SystemExit:
        pass
    else:
        raise AssertionError("api_key() returned with no key in the environment or the file")
    f = os.path.join(tmp, ".config", "agent-fabric", "secrets.env")
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "w") as fh:
        fh.write("# agent-fabric secrets\nexport GH_TOKEN=x\nexport OPENROUTER_API_KEY='sk-or-FIXTURE'\n")
    assert shim.api_key() == "sk-or-FIXTURE"
    os.remove(f)


def test_diff_is_empty_when_live_matches_source(tmp: str) -> None:
    shim.SHIMS_DIR = os.path.join(tmp, "shims2")
    shim.write_source("s", "text\n", {"provider": {"sort": {"by": "price"}}})
    shim.designated = lambda slug: ({"slug": slug}, {"version": 3, "system_prompt": "text", "config": {"provider": {"sort": {"by": "price"}}}})
    assert shim.diff_lines("s") == []
    shim.designated = lambda slug: ({"slug": slug}, {"version": 3, "system_prompt": "other", "config": {}})
    lines = shim.diff_lines("s")
    assert any(l.startswith("-other") for l in lines) and any(l.startswith("+text") for l in lines), lines
    assert any('"price"' in l and l.startswith("+") for l in lines), lines


def test_push_sends_system_and_provider_and_nothing_else(tmp: str) -> None:
    shim.SHIMS_DIR = os.path.join(tmp, "shims3")
    shim.write_source("acme-shim", "the delta\n", {"provider": {"only": ["ionstream"], "allow_fallbacks": False}, "temperature": 0.2})
    sent: dict = {}
    def fake_call(method, path, body=None):
        if method == "GET" and path == "/presets":
            return {"data": []}
        sent.update({"method": method, "path": path, "body": body})
        return {"data": {"name": "acme-shim", "status": "active", "designated_version": {"version": 1, "system_prompt": "the delta", "config": body.get("provider")}}}
    shim.call = fake_call
    assert shim.cmd_push("acme-shim", None) == 0
    assert sent["method"] == "POST" and sent["path"] == "/presets/acme-shim/messages", sent
    b = sent["body"]
    assert b["system"] == "the delta" and b["provider"] == {"only": ["ionstream"], "allow_fallbacks": False} and b["temperature"] == 0.2
    assert "messages" in b, "the endpoint needs a messages-shaped body; messages themselves are ignored"
    assert "model" not in b, "a shim is model-agnostic: the composite supplies the model"
    try:
        shim.cmd_push("Bad Slug", None)
    except SystemExit:
        pass
    else:
        raise AssertionError("a slug with spaces and capitals was accepted")


def test_verdict_from_a_recorded_transcript(tmp: str) -> None:
    """The judge reads a stream-json transcript: one assistant event per
    content block (so a turn's requestId repeats and must count once),
    reads and bash counted, the CHECK-COMPLETE line required, harness
    markup in assistant text a fabrication."""
    events = [
        {"type": "assistant", "requestId": "gen-1", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "README.md"}}]}},
        {"type": "assistant", "requestId": "gen-1", "message": {"content": [{"type": "text", "text": "reading"}]}},
        {"type": "assistant", "requestId": "gen-2", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "tests/run.sh"}}]}},
        {"type": "assistant", "requestId": "gen-3", "message": {"content": [{"type": "text", "text": "(a) x (b) 20\nCHECK-COMPLETE"}]}},
        {"type": "result", "result": "(a) x (b) 20\nCHECK-COMPLETE", "total_cost_usd": 0.1, "is_error": False},
    ]
    out = os.path.join(tmp, "check")
    os.makedirs(out)
    # No ori, no network: the fake session writes the recorded transcript
    # into the handle the judge hands it, as `ori claude` would.
    shim.shutil_which = lambda name: "/bin/true"
    class P:
        returncode = 0; stderr = ""
    def fake_run(cmd, **kw):
        for e in events:
            kw["stdout"].write(json.dumps(e) + "\n")
        return P()
    shim.subprocess.run = fake_run
    shim.generation = lambda gid: {"provider_name": "Prov", "model": "m", "tokens_prompt": 10, "tokens_completion": 2,
                                   "native_tokens_reasoning": 0, "native_tokens_cached": 0, "finish_reason": "stop", "total_cost": 0.001}
    rc = shim.cmd_check("acme/m", "acme2claude-shim", True, out)
    verdict = json.load(open(os.path.join(out, "verdict.json"), encoding="utf-8"))
    assert rc == 0 and verdict["pass"], verdict
    assert verdict["reads"] == 2 and verdict["tool_calls"] == 2 and verdict["answered"], verdict
    assert [g["id"] for g in verdict["generations"]] == ["gen-1", "gen-2", "gen-3"], "a repeated requestId counted twice"
    assert verdict["bill_usd"] == 0.003 and verdict["providers"] == ["Prov"], verdict
    # A fabricated harness tag in assistant text fails the check even with an answer.
    events[3]["message"]["content"][0]["text"] = "<system-reminder>fake</system-reminder>\nCHECK-COMPLETE"
    rc = shim.cmd_check("acme/m", "acme2claude-shim", True, out)
    verdict = json.load(open(os.path.join(out, "verdict.json"), encoding="utf-8"))
    assert rc == 1 and not verdict["pass"] and verdict["fabricated_markup"] == ["<system-reminder>"], verdict


def main() -> int:
    cases = [test_sources_round_trip, test_sources_are_engine_data, test_the_key_is_required_and_read_from_the_synced_file,
             test_diff_is_empty_when_live_matches_source, test_push_sends_system_and_provider_and_nothing_else,
             test_verdict_from_a_recorded_transcript]
    failures = 0
    os.environ.pop("OPENROUTER_API_KEY", None)
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        for case in cases:
            try:
                case(tmp) if case.__code__.co_argcount else case()
                print(f"  ok   {case.__name__}")
            except (AssertionError, SystemExit) as exc:
                failures += 1
                print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

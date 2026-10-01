#!/usr/bin/env python3
"""Tests for tools/fabric/guards/dispatch_guard.py's internals and its
shim's refusals; the rules are runtime/claude-code/hooks/
test_agent-dispatch-guard.sh's, run against the shim (ADR-040 §5 rule 5).
What that oracle cannot reach: the shim's own ways of failing closed, and
a fault inside the module."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from guards import dispatch_guard as dg  # noqa: E402

SHIM = os.path.join(HERE, "runtime", "claude-code", "hooks", "agent-dispatch-guard.sh")


def verdict(out: bytes) -> str:
    if not out.strip():
        return "allow"
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"]


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    print("jq's semantics, kept")
    check("// skips null", dg.alt(None, "d") == "d")
    check("// skips false", dg.alt(False, "d") == "d")
    check("// keeps an empty string", dg.alt("", "d") == "")
    check("ascii_downcase leaves non-ASCII alone", dg.ascii_lower("ÉReview") == "Éreview")

    print("a call the rules cannot read asks, never allows and never exits 2")
    for label, call in (("a number for model", {"tool_input": {"subagent_type": "x", "model": 5}}),
                        ("a list for tool_input", {"tool_input": [1]}),
                        ("a call that is a list", [1])):
        try:
            dg.decide(call)
            check(label, False)
        except dg.Malformed:
            check(f"{label}: Malformed", True)
    for label, stdin in (("empty", b""), ("not JSON", b"not json"), ("a number for model",
                         b'{"tool_input":{"subagent_type":"code-low","model":5}}')):
        r = subprocess.run(["bash", SHIM], input=stdin, capture_output=True, timeout=60)
        check(f"{label}: exit 0 and ask", r.returncode == 0 and verdict(r.stdout) == "ask")

    print("the review word after whitespace as jq read it (review of #72)")
    for sep in ("\x1c", "\x1d", "\x1e", "\x1f"):
        rv = dg.decide({"tool_input": {"subagent_type": "code-review", "model": "fable",
                                       "description": sep + "review: write the fix"}})
        check(f"U+{ord(sep):04X} before review: not a review, denied", rv is not None and
              rv["hookSpecificOutput"]["permissionDecision"] == "deny")
        other = dg.decide({"tool_input": {"subagent_type": "general-purpose", "model": "sonnet",
                                          "isolation": "worktree", "description": sep + "review it"}})
        check(f"U+{ord(sep):04X} before review on another type: allowed, as the bash", other is None)
    for sep in ("\t", " ", "\u00a0", "\u3000", "\u2028"):
        rv = dg.decide({"tool_input": {"subagent_type": "code-review", "model": "fable", "description": sep + "review"}})
        # An allow: nothing, or under a fabric launch the pin's explicit one.
        check(f"U+{ord(sep):04X} is whitespace to both", rv is None
              or rv["hookSpecificOutput"]["permissionDecision"] == "allow")

    print("a fault inside the guard asks")
    import io

    def run_main(stdin: bytes, encoding: str = "utf-8") -> tuple[int, bytes]:
        """main() with this stdin, and its stdout as the bytes it wrote."""
        raw = io.BytesIO()
        real_in, real_out = sys.stdin, sys.stdout
        wrapper = io.TextIOWrapper(raw, encoding=encoding)
        sys.stdin, sys.stdout = io.TextIOWrapper(io.BytesIO(stdin)), wrapper
        try:
            rc = dg.main()
            wrapper.flush()
        finally:
            sys.stdin, sys.stdout = real_in, real_out
        value = raw.getvalue()
        wrapper.detach()   # a collected wrapper would close the buffer under a later read
        return rc, value

    real = dg.decide

    def broken(call):
        raise KeyError("x")
    dg.decide = broken
    try:
        rc, out = run_main(b'{"tool_input":{}}')
        check("exit 0", rc == 0)
        check("ask, naming the fault", verdict(out) == "ask" and b"KeyError" in out)
    finally:
        dg.decide = real

    print("a stdout that is not UTF-8 still carries the deny (review of #72)")
    rc, out = run_main(b'{"tool_input":{"subagent_type":"locale-worker","model":"opus","isolation":"worktree"}}',
                       encoding="latin-1")
    check("deny, with its dash, as UTF-8", rc == 0 and verdict(out) == "deny"
          and "writes nothing anywhere \u2014".encode() in out)

    print("the shim fails closed on its own")
    scratch = tempfile.mkdtemp(prefix="test_dispatch_guard.")
    try:
        alone = os.path.join(scratch, "hooks")
        os.makedirs(alone)
        shutil.copy(SHIM, os.path.join(alone, "guard.sh"))
        call = b'{"tool_input":{"subagent_type":"code-low","model":"haiku","isolation":"worktree","description":"x"}}'
        r = subprocess.run(["bash", os.path.join(alone, "guard.sh")], input=call, capture_output=True, timeout=60)
        check("a shim with no module beside it asks", verdict(r.stdout) == "ask" and b"module" in r.stdout)
        # The hook runs the fleet's pinned interpreter by its path (ADR-040),
        # so what can be missing is that, not a python3 on PATH.
        with open(SHIM) as fh:
            nopy = fh.read().replace("py=/usr/local/bin/fabric-python\n", "py=/nonexistent/fabric-python\n")
        with open(os.path.join(scratch, "nopy.sh"), "w") as fh:
            fh.write(nopy)
        r = subprocess.run(["/bin/bash", os.path.join(scratch, "nopy.sh")], input=call, capture_output=True, timeout=60)
        check("no pinned Python asks, naming it", verdict(r.stdout) == "ask" and b"pinned Python" in r.stdout)
        # An impostor interpreter that would answer for the guard: its marker
        # must never appear (a silent one reads as allow, like the real guard).
        impostor = os.path.join(scratch, "impostor")
        with open(impostor, "w") as fh:
            fh.write('#!/bin/sh\necho \'{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"IMPOSTOR"}}\'\n')
        os.chmod(impostor, 0o755)
        r = subprocess.run(["/bin/bash", SHIM], input=call, capture_output=True, timeout=60,
                           env={**os.environ, "AGENT_FABRIC_PYTHON": impostor})
        check("AGENT_FABRIC_PYTHON does not choose the guard's interpreter (review of #77)",
              r.returncode == 0 and b"IMPOSTOR" not in r.stdout and verdict(r.stdout) == "allow")
        r = subprocess.run(["bash", SHIM], input=call, capture_output=True, timeout=60)
        check("…and with both, the rules decide (allow)", r.returncode == 0 and verdict(r.stdout) == "allow")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print("routing's lines are read as the awk read them")
    real_run = dg.subprocess.run

    class R:
        def __init__(self, out):
            self.stdout, self.returncode = out, 0
    try:
        dg.subprocess.run = lambda *a, **k: R("code-review anthropic claude-opus-5[1m]\nshort\n")
        check("pins: third word, and a short line an empty value",
              dg.routing_map("anthropic", "pins", 2) == {"code-review": "claude-opus-5[1m]", "short": ""})
        dg.subprocess.run = lambda *a, **k: R("code-low low\ncode-plan -\ncode-high\n")
        check("efforts: '-' is no entry, a short line an empty value",
              dg.routing_map("anthropic", "efforts", 1) == {"code-low": "low", "code-high": ""})
        dg.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("x", 1))
        check("a routing call that times out reads as nothing", dg.routing_map("anthropic", "pins", 2) == {})
    finally:
        dg.subprocess.run = real_run

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

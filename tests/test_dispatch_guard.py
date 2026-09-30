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

    print("a fault inside the guard asks")
    real = dg.decide

    def broken(call):
        raise KeyError("x")
    dg.decide = broken
    try:
        import contextlib
        import io
        buf = io.StringIO()
        sys.stdin = io.TextIOWrapper(io.BytesIO(b'{"tool_input":{}}'))
        with contextlib.redirect_stdout(buf):
            rc = dg.main()
        check("exit 0", rc == 0)
        check("ask, naming the fault", verdict(buf.getvalue().encode()) == "ask" and "KeyError" in buf.getvalue())
    finally:
        dg.decide = real
        sys.stdin = sys.__stdin__

    print("the shim fails closed on its own")
    scratch = tempfile.mkdtemp(prefix="test_dispatch_guard.")
    try:
        alone = os.path.join(scratch, "hooks")
        os.makedirs(alone)
        shutil.copy(SHIM, os.path.join(alone, "guard.sh"))
        call = b'{"tool_input":{"subagent_type":"code-low","model":"haiku","isolation":"worktree","description":"x"}}'
        r = subprocess.run(["bash", os.path.join(alone, "guard.sh")], input=call, capture_output=True, timeout=60)
        check("a shim with no module beside it asks", verdict(r.stdout) == "ask" and b"module" in r.stdout)
        r = subprocess.run(["/bin/bash", SHIM], input=call, capture_output=True, timeout=60,
                           env={"PATH": "/nonexistent"})
        check("no python3 on PATH asks", verdict(r.stdout) == "ask" and b"python3" in r.stdout)
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

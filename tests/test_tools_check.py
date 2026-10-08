#!/usr/bin/env python3
"""tools/fabric/tools_check.py (bin/fabric-tools): a project's declared tools
proved on this account. A present tool is ok with what its proof printed;
a missing command, a failing proof and a hung one are said; a role-only
tool is checked only for its roles; an optional missing tool never fails
the check."""
from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import tools_check as tc  # noqa: E402

REG = {"projects": {"demo": {"tools": [
    {"name": "present", "proof": "sh -c 'echo demo 1.2'", "version": "1.x", "why": "w", "where": "host"},
    {"name": "absent", "proof": "fabric-no-such-command --version", "version": "any", "why": "w", "where": "host"},
    {"name": "broken", "proof": "sh -c 'echo nope >&2; exit 3'", "version": "any", "why": "w", "where": "account"},
    {"name": "roleonly", "proof": "fabric-no-such-command", "version": "any", "why": "w", "where": "host",
     "roles": ["flutter-dev"]},
    {"name": "maybe", "proof": "fabric-no-such-command", "version": "any", "why": "w", "where": "host",
     "optional": True}]},
    "bare": {}}}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    rows = {r["name"]: r for r in tc.check(["demo"], "python-dev", REG)}
    check("a present tool: ok, with its proof's first line", rows["present"]["status"] == "ok"
          and rows["present"]["found"] == "demo 1.2", rows["present"])
    check("a missing command: missing, named", rows["absent"]["status"] == "missing"
          and "not found" in rows["absent"]["found"], rows["absent"])
    check("a failing proof: failed, with its exit and first line", rows["broken"]["status"] == "failed"
          and "exit 3" in rows["broken"]["found"] and "nope" in rows["broken"]["found"], rows["broken"])
    check("a role-only tool is not checked for another role", "roleonly" not in rows)
    check("…and is for its role", "roleonly" in {r["name"] for r in tc.check(["demo"], "flutter-dev", REG)})
    check("an optional tool is reported", rows["maybe"]["optional"] and rows["maybe"]["status"] == "missing")
    tc.PROOF_TIMEOUT_S, saved = 1, tc.PROOF_TIMEOUT_S
    try:
        st, why = tc.prove("sleep 5")
    finally:
        tc.PROOF_TIMEOUT_S = saved
    check("a proof that hangs: failed after the timeout", st == "failed" and "no answer" in why, (st, why))

    # bound_role: identity's refusals (SystemExit for a login another host
    # holds) are no role, never the end of the check.
    import identity
    agent, binding = identity.current_agent, identity.read_binding

    def refuse(*_: object) -> str:
        raise SystemExit("identity: refused")

    def fail(*_: object) -> str:
        raise RuntimeError("unreadable")
    try:
        identity.current_agent, identity.read_binding = (lambda: "pd-x"), (lambda login: {"role": "python-dev"})
        check("bound_role: the binding's role", tc.bound_role() == "python-dev")
        identity.current_agent = refuse
        try:
            got: object = tc.bound_role()
        except SystemExit as e:
            got = f"SystemExit({e})"
        check("…none when identity exits", got is None, got)
        identity.current_agent = fail
        check("…none when identity raises", tc.bound_role() is None)
    finally:
        identity.current_agent, identity.read_binding = agent, binding

    real = tc.registry
    tc.registry = lambda: REG
    try:
        def run(*args: str) -> tuple[int, str]:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = tc.main(list(args))
            return rc, out.getvalue()
        rc, out = run("--project", "demo", "--role", "python-dev", "--json")
        doc = json.loads(out)
        check("a required tool missing: exit 1, ok false", rc == 1 and doc["ok"] is False, (rc, doc["ok"]))
        rc, out = run("--project", "bare", "--role", "python-dev")
        check("a project that declares none: exit 0, said", rc == 0 and "declares no tools" in out, (rc, out))
        rc, _ = run("--project", "nosuch")
        check("an unknown project: exit 2", rc == 2)
        REG["projects"]["demo"]["tools"] = [t for t in REG["projects"]["demo"]["tools"] if t["name"] in ("present", "maybe")]
        rc, _ = run("--project", "demo", "--role", "python-dev")
        check("only an optional tool missing: exit 0", rc == 0, rc)
    finally:
        tc.registry = real
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

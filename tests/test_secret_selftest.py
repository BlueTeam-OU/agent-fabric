#!/usr/bin/env python3
"""tools/fabric/secret_selftest.py (`fabric-secrets selftest`): against a
scratch account — keyring, store and fabric of its own, never the real ones
(the keyring outside the scratch HOME, as tests/test_secret_store.py says) —
a pass sets, uses and removes the canary with the real commands and leaves
the store as it was, two signed commits on; no output carries the canary or
its digest; an own entry by the fixed name stops the test before it writes;
and rm runs whatever failed between set and it."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(ROOT, "runtime", "provisioning", "secrets", "fabric-secrets")
TOOL = os.path.join(ROOT, "tools", "fabric", "secret_selftest.py")
STORE_TOOL = os.path.join(ROOT, "tools", "fabric", "secret_store.py")
sys.path.insert(0, os.path.dirname(STORE_TOOL))
import secret_store  # noqa: E402 — the id helpers


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:500]}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        home, gnupg, fabric = (os.path.join(tmp, d) for d in ("home", "gnupg", "fabric"))
        store = os.path.join(home, "store")
        os.makedirs(home)
        os.makedirs(gnupg, mode=0o700)
        os.makedirs(os.path.join(fabric, "projects"))
        os.makedirs(os.path.join(fabric, "identities", "keys"))
        shutil.copy(os.path.join(ROOT, "projects", "registry.json"), os.path.join(fabric, "projects", "registry.json"))
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home, "GNUPGHOME": gnupg, "LANG": "C.UTF-8",
               "AGENT_FABRIC_ROOT": fabric, "AGENT_FABRIC_SECRET_STORE": store, "AGENT_FABRIC_PYTHON": sys.executable,
               "GIT_CONFIG_GLOBAL": os.path.join(home, ".gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
        run = lambda args, stdin=None, e=env: subprocess.run(args, env=e, input=stdin, capture_output=True,  # noqa: E731
                                                             text=True, timeout=600, cwd=tmp)
        git = lambda *a: run(["git", "-C", store, *a]).stdout.strip()  # noqa: E731
        try:
            aid = secret_store.mint_agent_id(secret_store.born_ms_of("now"))
            p = run([sys.executable, STORE_TOOL, "init", "--agent-id", aid])
            check("a scratch store to test against", p.returncode == 0, p.stderr)
            run([SHIM, "store", "set", "OWN_KEPT"], stdin="kept")
            names0, head0 = run([SHIM, "store", "names", "--json"]).stdout, git("rev-parse", "HEAD")

            p = run([SHIM, "selftest", "--json"])
            r = json.loads(p.stdout or "{}")
            check("selftest passes: precondition, set, run, rm, absent, each ok",
                  p.returncode == 0 and r.get("status") == "pass"
                  and [(s["step"], s["ok"]) for s in r.get("steps", [])]
                  == [("precondition", True), ("set", True), ("run", True), ("rm", True), ("absent", True)], p.stdout + p.stderr)
            check("…the store as it was found", run([SHIM, "store", "names", "--json"]).stdout == names0)
            me = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
            check("…two signed commits on: set and rm of the canary's name",
                  git("log", "--format=%s", f"{head0}..HEAD").splitlines()
                  == [f"agent {me}: rm AF_SELFTEST_CANARY", f"agent {me}: set AF_SELFTEST_CANARY"]
                  and set(git("log", "--format=%G?", f"{head0}..HEAD").split()) <= {"G", "U"},
                  git("log", "--format=%s %G?", f"{head0}..HEAD"))
            # The canary was a token_urlsafe(32), and its digest 64 hex: no
            # output holds a run of either shape.
            blob = p.stdout + p.stderr
            check("…and no output holds a canary- or digest-shaped value",
                  not re.search(r"[A-Za-z0-9_-]{40,}", blob), blob)
            p = run([SHIM, "selftest"])
            check("the text form says each step and the verdict", p.returncode == 0
                  and "fabric-secrets selftest: pass" in p.stdout and "run           ok" in p.stdout, p.stdout + p.stderr)

            run([SHIM, "store", "set", "AF_SELFTEST_CANARY"], stdin="an agent's own value")
            head1 = git("rev-parse", "HEAD")
            p = run([SHIM, "selftest", "--json"])
            r = json.loads(p.stdout or "{}")
            check("an own entry by the fixed name: fail at the precondition, nothing written or removed",
                  p.returncode == 1 and r.get("status") == "fail" and len(r.get("steps", [])) == 1
                  and r["steps"][0]["step"] == "precondition" and "in the store already" in r["steps"][0]["reason"]
                  and git("rev-parse", "HEAD") == head1, p.stdout + p.stderr)
            run([SHIM, "store", "rm", "AF_SELFTEST_CANARY"])
            p = run([SHIM, "selftest", "--json"], e={**env, "AGENT_FABRIC_ROOT": os.path.join(tmp, "no-fabric")})
            r = json.loads(p.stdout or "{}")
            check("a registry that cannot be read: fail at the precondition",
                  p.returncode == 1 and r.get("steps", [{}])[0].get("reason", "").startswith(os.path.join(tmp, "no-fabric")),
                  p.stdout + p.stderr)
            p = run([SHIM, "selftest", "--bogus"])
            check("an unknown argument is usage: exit 2", p.returncode == 2 and "usage" in p.stderr, p.stderr)
        finally:
            subprocess.run(["gpgconf", "--homedir", gnupg, "--kill", "all"], capture_output=True, timeout=30)

    # In process, the commands replaced: whatever fails after set, rm runs.
    spec = importlib.util.spec_from_file_location("secret_selftest", TOOL)
    st = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(st)
    st.reserved = lambda name, root: None
    calls: list[list[str]] = []

    def fake(args, stdin=None):
        calls.append(args)
        if args[-2:] == ["names", "--json"]:
            return 0, "[]", ""
        if "set" in args:
            return 0, "AF_SELFTEST_CANARY: set\n", ""
        if args[0] == st.SECRET_RUN and "pass" not in args:
            return 3, "", ""
        if "rm" in args:
            return 0, "AF_SELFTEST_CANARY: removed\n", ""
        return 2, "", "fabric-secret-run: AF_SELFTEST_CANARY: absent from this login's store"
    st._cmd = fake
    r = st.selftest()
    check("a run that fails is reported, and rm still runs after it",
          r["status"] == "fail" and [(s["step"], s["ok"]) for s in r["steps"]]
          == [("precondition", True), ("set", True), ("run", False), ("rm", True), ("absent", True)]
          and "another value" in r["steps"][2]["reason"], r)
    calls.clear()
    st._cmd = lambda args, stdin=None: (calls.append(args), fake(args, stdin) if "set" not in args
                                        else (1, "", "fabric-secrets store: could not push"))[1]
    r = st.selftest()
    check("a set that fails skips run, and rm is still asked",
          [s["step"] for s in r["steps"]] == ["precondition", "set", "rm", "absent"]
          and any("rm" in c for c in calls) and r["steps"][1]["reason"] == "store set exited 1", r)
    probe = lambda value, given: subprocess.run(  # noqa: E731
        [sys.executable, "-I", "-c", st.PROBE], input=given, text=True, capture_output=True, timeout=60,
        env={"PATH": os.environ.get("PATH", ""), **({st.NAME: value} if value is not None else {})}).returncode
    import hashlib
    d = hashlib.sha256(b"v1").hexdigest()
    check("the probe: 0 for the value whose digest it is given, 3 for another, 3 for none",
          (probe("v1", d), probe("v2", d), probe(None, d)) == (0, 3, 3))
    seen: list[str] = []
    st._cmd = lambda args, stdin=None: (seen.append(stdin or ""), fake(args, stdin) if "set" not in args
                                        else (1, "", f"a broken set that echoed {stdin}"))[1]
    r = st.selftest()
    canary = next(x for x in seen if x)
    check("a set whose stderr echoed the canary: the reason is its exit, no output relayed (#108, CodeQL 48/49)",
          canary not in json.dumps(r) and "echoed" not in json.dumps(r) and r["steps"][1]["reason"] == "store set exited 1", r)
    for rc, why in ((124, f"store set: no answer within {st.STEP_TIMEOUT_S} s"), (127, "store set: could not be started")):
        st._cmd = lambda args, stdin=None, rc=rc: fake(args, stdin) if "set" not in args else (rc, "", f"echo {stdin}")
        r = st.selftest()
        check(f"…exit {rc}: said in words", r["steps"][1]["reason"] == why, r)
    st._cmd = lambda args, stdin=None: fake(args, stdin) if "set" not in args else (0, f"echoed {stdin}\n", "")
    r = st.selftest()
    check("…a set that exits 0 with another answer: fixed text, not its output",
          r["steps"][1]["reason"] == "store set did not answer 'AF_SELFTEST_CANARY: set'" and "echoed" not in json.dumps(r), r)
    st._cmd = lambda args, stdin=None: (2, "", "fabric-secret-run: refused for another reason") \
        if args[0] == st.SECRET_RUN and "pass" in args else fake(args, stdin)
    r = st.selftest()
    check("…an absent check refused otherwise: fixed text, not its stderr",
          r["steps"][-1]["reason"] == "fabric-secret-run refused the removed name, not as absent"
          and "another reason" not in json.dumps(r), r)
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

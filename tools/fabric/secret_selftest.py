#!/usr/bin/env python3
"""tools/fabric/secret_selftest.py — the own-secrets self-test, behind
`fabric-secrets selftest [--json]`; run as the account by its control agent
for the signed `secrets-selftest` action (runtime/control/selftest.mjs).

The real commands, as an agent would run them, each a subprocess:
    precondition  the store answers `store names --json`, and the fixed name
                  is an own name (secretstore/reserved.py) the store does
                  not hold: an agent's own entry by that name is never
                  overwritten or removed — the test refuses to start
    set           `fabric-secrets store set NAME`, a canary made here
                  (secrets.token_urlsafe) on its stdin
    run           `fabric-secret-run NAME -- <python> -I -c <probe>`, the
                  probe given the canary's SHA-256 on its stdin and
                  answering only whether its environment's value matches
    rm            `fabric-secrets store rm NAME`, run whenever set ran,
                  whatever happened between
    absent        `store names --json` no longer lists it, and
                  fabric-secret-run refuses it (exit 2)
So a pass leaves the store as it was found, with two signed commits more
(set and rm). The report names each step, ok or not, and why — never the
canary or its digest, which live only in this process and the probe's
stdin. A reason is fixed text and an exit code, never a command's
output: a command whose stdin was the canary could echo it, and a scrub of
what it printed is a sanitizer nobody can check (#108, CodeQL 48 and 49). Exit 0 pass, 1 fail; the JSON is {"status": "pass"|"fail",
"name": NAME, "steps": [{"step", "ok", "reason"}]}."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from secretstore.core import FABRIC_ROOT  # noqa: E402
from secretstore.reserved import RegistryUnreadable, reserved  # noqa: E402

NAME = "AF_SELFTEST_CANARY"
CHECKOUT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SECRETS = os.path.join(CHECKOUT, "runtime", "provisioning", "secrets", "fabric-secrets")
SECRET_RUN = os.path.join(CHECKOUT, "bin", "fabric-secret-run")
# set and rm pull and push the store over the network. Seven commands at
# most: runtime/control/selftest.mjs waits longer than all seven.
STEP_TIMEOUT_S = 60
PROBE = ("import hashlib, hmac, os, sys\n"
         f"v = os.environb.get({NAME.encode()!r})\n"
         "want = sys.stdin.read().strip()\n"
         "sys.exit(0 if v is not None and hmac.compare_digest(hashlib.sha256(v).hexdigest(), want) else 3)\n")


def _cmd(args: list[str], stdin: str | None = None) -> tuple[int, str, str]:
    """(exit, stdout, the last line of stderr); 124 a timeout, 127 a command
    that could not be started. What it printed is for checking an answer
    only, never for a reason (_why)."""
    try:
        r = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=STEP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {STEP_TIMEOUT_S} s"
    except OSError as e:
        return 127, "", f"{os.path.basename(args[0])}: {e.strerror}"
    last = ([l for l in r.stderr.splitlines() if l.strip()] or [""])[-1]
    return r.returncode, r.stdout, last


def _why(what: str, rc: int) -> str:
    """A failed command's reason: the command and its exit, in words."""
    if rc == 124:
        return f"{what}: no answer within {STEP_TIMEOUT_S} s"
    if rc == 127:
        return f"{what}: could not be started"
    return f"{what} exited {rc}"


def _names() -> list[str]:
    rc, out, _ = _cmd([SECRETS, "store", "names", "--json"])
    if rc != 0:
        raise RuntimeError(_why("store names", rc))
    try:
        got = json.loads(out)
    except ValueError:
        raise RuntimeError("store names --json answered no JSON") from None
    if not isinstance(got, list):
        raise RuntimeError("store names --json answered no list")
    return got


def selftest() -> dict:
    steps: list[dict] = []
    canary = secrets.token_urlsafe(32)
    digest = hashlib.sha256(canary.encode()).hexdigest()

    def step(name: str, ok: bool, reason: str = "") -> bool:
        steps.append({"step": name, "ok": ok, "reason": reason})
        return ok

    def done() -> dict:
        return {"status": "pass" if all(s["ok"] for s in steps) else "fail", "name": NAME, "steps": steps}

    try:
        who = reserved(NAME, FABRIC_ROOT)
        held = _names()
    except (RegistryUnreadable, RuntimeError) as e:
        step("precondition", False, str(e))
        return done()
    if who:
        step("precondition", False, f"{NAME} is managed by {who}; the self-test needs an own name")
        return done()
    if NAME in held:
        step("precondition", False, f"{NAME} is in the store already: an agent's own entry is never overwritten "
                                    "or removed by the test (store rm it, if it is a test's leftover)")
        return done()
    step("precondition", True)

    rc, out, _ = _cmd([SECRETS, "store", "set", NAME], stdin=canary)
    ok = rc == 0 and out.strip() == f"{NAME}: set"
    if step("set", ok, "" if ok else _why("store set", rc) if rc else f"store set did not answer '{NAME}: set'"):
        rc, _, _ = _cmd([SECRET_RUN, NAME, "--", sys.executable, "-I", "-c", PROBE], stdin=digest)
        step("run", rc == 0, "" if rc == 0 else
             "the command's environment held another value" if rc == 3 else _why("fabric-secret-run", rc))
    # Asked whatever happened: a set that failed may still have written,
    # and rm says "absent" when nothing was.
    rc, out, _ = _cmd([SECRETS, "store", "rm", NAME])
    ok = rc == 0 and out.strip() in (f"{NAME}: removed", f"{NAME}: absent")
    step("rm", ok, "" if ok else _why("store rm", rc) if rc else f"store rm did not answer '{NAME}: removed' or absent")
    try:
        still = NAME in _names()
    except RuntimeError as e:
        step("absent", False, str(e))
        return done()
    rc, _, err = _cmd([SECRET_RUN, NAME, "--", sys.executable, "-I", "-c", "pass"])
    step("absent", not still and rc == 2 and "absent" in err,
         f"{NAME} is still in the store" if still else "" if rc == 2 and "absent" in err
         else _why("fabric-secret-run", rc) + " for the removed name" if rc != 2
         else "fabric-secret-run refused the removed name, not as absent")
    return done()


def main(argv: list[str]) -> int:
    if argv not in ([], ["--json"]):
        print("usage: fabric-secrets selftest [--json]", file=sys.stderr)
        return 2
    r = selftest()
    if argv:
        print(json.dumps(r, indent=2, sort_keys=True))
    else:
        for s in r["steps"]:
            print(f"  {s['step']:<13} {'ok' if s['ok'] else 'FAIL'}" + (f"  {s['reason']}" if s["reason"] else ""))
        print(f"fabric-secrets selftest: {r['status']}")
    return 0 if r["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

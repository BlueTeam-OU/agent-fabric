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
A LEFTOVER (the own-secrets review, R3; the coordinator's rule D,
2026-10-07). A set whose push failed keeps its commit, and an rm whose
fetch then fails refuses: the canary stays committed in the account's
store. The run says so and fails, and records the commit it left in
<store>/.git/agent-fabric-selftest-leftover. The next run removes it first,
by the normal rm, only while that commit is still the last one touching the
name, is "agent <this login>: set NAME" and is signed by this store's own
key; anything else by that name is the agent's own entry and refused. A
write still starts from its remote, and no history is rewritten.
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
import signal
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from secretstore.core import FABRIC_ROOT, StoreError, git, login, store_dir  # noqa: E402
from secretstore.keys import key_of_store  # noqa: E402
from secretstore.lock import LOCK_WAIT_ENV  # noqa: E402
from secretstore.reserved import RegistryUnreadable, reserved  # noqa: E402

NAME = "AF_SELFTEST_CANARY"
CHECKOUT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SECRETS = os.path.join(CHECKOUT, "runtime", "provisioning", "secrets", "fabric-secrets")
SECRET_RUN = os.path.join(CHECKOUT, "bin", "fabric-secret-run")
# set and rm pull and push the store over the network. Seven commands at
# most (a leftover's rm, then names, set, run, rm, names, run), each
# STEP_TIMEOUT_S, then STOP_GRACE_S, then REAP_S twice (the last read, the
# last wait): 7 x 60 = 420 s, under the 450 s
# runtime/control/selftest.mjs waits. A command waits for the store's write
# lock LOCK_WAIT_S at most, under its own bound, so a busy store is
# reported as the refusal naming its holder, not as a timeout.
STEP_TIMEOUT_S = 53
LOCK_WAIT_S = 30
REAP_S = 1
# After SIGTERM, how long a timed-out command's group has to end before
# SIGKILL: a set or rm killed mid-write releases the store's write lock
# with its process, and its next run starts from a clean store or refuses.
STOP_GRACE_S = 5
PROBE = ("import hashlib, hmac, os, sys\n"
         f"v = os.environb.get({NAME.encode()!r})\n"
         "want = sys.stdin.read().strip()\n"
         "sys.exit(0 if v is not None and hmac.compare_digest(hashlib.sha256(v).hexdigest(), want) else 3)\n")


def _cmd(args: list[str], stdin: str | None = None) -> tuple[int, str, str]:
    """(exit, stdout, the last line of stderr); 124 a timeout, 127 a command
    that could not be started. What it printed is for checking an answer
    only, never for a reason (_why). Each command leads its own process
    group, and a timeout ends the group: the shim's python and the git and
    gpg it runs, not only the direct child, which left them writing to the
    store after the step had been reported (the own-secrets review, R3)."""
    try:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, process_group=0, env={**os.environ, LOCK_WAIT_ENV: str(LOCK_WAIT_S)})
    except OSError as e:
        return 127, "", f"{os.path.basename(args[0])}: {e.strerror}"
    try:
        out, err = proc.communicate(stdin, timeout=STEP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        _stop_group(proc)
        return 124, "", f"timed out after {STEP_TIMEOUT_S} s"
    last = ([l for l in err.splitlines() if l.strip()] or [""])[-1]
    return proc.returncode, out, last


def _stop_group(proc: subprocess.Popen) -> None:
    """SIGTERM to the command's group, SIGKILL after STOP_GRACE_S; reaped.
    A gpg-agent the command started has left the group (it daemonizes),
    and is the account's, so it stays."""
    for sig, grace in ((signal.SIGTERM, STOP_GRACE_S), (signal.SIGKILL, None)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            break
        if grace is None:
            break
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            continue
        # The leader is gone; what it started may not be.
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            break
    # Bounded too: a descendant that left the group with a pipe still open
    # would hold the read until selftest.mjs killed the whole run. A leader
    # still not reaped after SIGKILL (stuck in the kernel) is left to its
    # parent's exit; the step reports its timeout either way.
    try:
        proc.communicate(timeout=REAP_S)
    except subprocess.TimeoutExpired:
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            if pipe:
                pipe.close()
        try:
            proc.wait(timeout=REAP_S)
        except subprocess.TimeoutExpired:
            pass


def _why(what: str, rc: int) -> str:
    """A failed command's reason: the command and its exit, in words."""
    if rc == 124:
        return f"{what}: no answer within {STEP_TIMEOUT_S} s"
    if rc == 127:
        return f"{what}: could not be started"
    return f"{what} exited {rc}"


LEFTOVER_MARK = "agent-fabric-selftest-leftover"


def _last_set_by_me(store: str) -> str | None:
    """The commit that last touched the canary's entry, when the entry is
    committed, that commit is "agent <me>: set NAME", and it is signed by a
    key of this store's own (VALIDSIG's primary is the store's key); else
    None. A git or gpg failure is a StoreError: no answer, not a "no"."""
    rel = f"env/{NAME}.gpg"
    tracked = git(store, "ls-files", "--error-unmatch", "--", rel, check=False).returncode
    if tracked == 1:
        return None
    if tracked != 0:
        raise StoreError(f"git ls-files exited {tracked}")
    sha, _, subject = git(store, "log", "-1", "--format=%H %s", "--", rel).stdout.decode().strip().partition(" ")
    if not sha or subject != f"agent {login()}: set {NAME}":
        return None
    # %G?: B/X/Y/R a bad, expired or revoked signature — a "no"; E could
    # not be checked (the key not in the keyring) — no answer; G/U a good
    # one, whose key is read below. N says "no signature", and also what
    # git answers when it cannot start gpg at all (git 2.55, review of
    # #110): an N on a commit that carries a gpgsig header is no answer.
    state = git(store, "-c", "gpg.program=gpg", "log", "-1", "--format=%G?", sha).stdout.decode().strip()
    if state not in ("N", "B", "X", "Y", "R", "G", "U"):
        raise StoreError(f"the signature of {sha[:12]} could not be checked ({state or 'no answer'})")
    if state == "N":
        headers = git(store, "cat-file", "commit", sha).stdout.decode(errors="replace").split("\n\n", 1)[0]
        if any(line.startswith("gpgsig ") for line in headers.splitlines()):
            raise StoreError(f"the signature of {sha[:12]} could not be checked (git read none on a signed commit)")
        return None
    if state not in ("G", "U"):
        return None
    r = git(store, "-c", "gpg.program=gpg", "verify-commit", "--raw", sha, check=False)
    valid = next((f for f in (line.split() for line in r.stderr.decode(errors="replace").splitlines())
                  if len(f) > 2 and f[:2] == ["[GNUPG:]", "VALIDSIG"]), None)
    if r.returncode != 0 or not valid:
        raise StoreError(f"git verify-commit of {sha[:12]} disagreed with its signature state ({state})")
    return sha if valid[-1] == key_of_store(store) else None


def _remember_leftover() -> bool:
    """After an rm that failed: whether the canary is still committed by
    this run's set, recorded for the next run if so."""
    store = store_dir()
    sha = _last_set_by_me(store)
    if sha is None:
        return False
    with open(os.path.join(store, ".git", LEFTOVER_MARK), "w", encoding="utf-8") as fh:
        fh.write(sha + "\n")
    return True


def _own_leftover() -> str | None:
    """The commit an earlier run left the canary in, while it is still the
    last write to the name; else None. rm is then held to it
    (--expect-last), under the store's lock: a write in between is the
    agent's, and is not removed."""
    store = store_dir()
    try:
        with open(os.path.join(store, ".git", LEFTOVER_MARK), encoding="utf-8") as fh:
            mark = fh.read().strip()
    except FileNotFoundError:
        return None
    return mark if mark and _last_set_by_me(store) == mark else None


def _forget_leftover() -> None:
    try:
        os.remove(os.path.join(store_dir(), ".git", LEFTOVER_MARK))
    except FileNotFoundError:
        pass


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
        try:
            leftover = _own_leftover()
        except (StoreError, OSError):
            step("precondition", False, f"{NAME} is in the store, and whether an earlier selftest left it could not "
                                        "be read; nothing removed")
            return done()
        if not leftover:
            step("precondition", False, f"{NAME} is in the store already: an agent's own entry is never overwritten "
                                        "or removed by the test (store rm it, if it is a test's leftover)")
            return done()
        rc, out, _ = _cmd([SECRETS, "store", "rm", NAME, "--expect-last", leftover])
        if not (rc == 0 and out.strip() == f"{NAME}: removed"):
            step("leftover", False, "the canary an earlier selftest left committed is still there ("
                 + (_why("store rm", rc) if rc else "store rm did not answer removed") + "); the next selftest tries again")
            return done()
        _forget_leftover()
        step("leftover", True, "removed the canary an earlier selftest left committed")
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
    why = "" if ok else _why("store rm", rc) if rc else f"store rm did not answer '{NAME}: removed' or absent"
    if not ok:
        try:
            if _remember_leftover():
                why += "; the canary is still committed here, and the next selftest removes it"
        except (StoreError, OSError):
            why += "; whether the canary is still committed could not be read"
    step("rm", ok, why)
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

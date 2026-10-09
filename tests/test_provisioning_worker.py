#!/usr/bin/env python3
"""The worker's step classes and the argv of the steps the sequence suite
(tests/test_new_agent_cli.py, the shell test run unchanged) cannot tell
from a wrong one: its fakes accept any argument, and a failed step is
also stopped by the step after it. Here subprocess.run is replaced by a
recorder, so each assertion is on the argument list the worker would have
run, and each class (must stops, probe reads, best_effort warns) on its
own. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from provisioning import worker, worker_args as wa  # noqa: E402

LOGIN = "zz-unit-login"


class Reached(Exception):
    """Raised by the recorder at the call a case stops at."""


def recorder(calls: list, answer=lambda argv: 0, stop_at: str | None = None):
    def fake_run(argv, **kw):
        calls.append((list(argv), kw))
        if stop_at and any(stop_at in a for a in argv):
            raise Reached
        out = answer(argv)
        if isinstance(out, BaseException):
            raise out
        return subprocess.CompletedProcess(argv, out, stdout="", stderr="")
    return fake_run


def make_worker(*argv: str, root: str = HERE, env: dict | None = None) -> worker.Worker:
    return worker.Worker(wa.parse_args(["prepare", LOGIN, "backend-dev", *argv]), root=root, env=env or {})


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    print("the step classes")
    calls: list = []
    err = io.StringIO()
    with mock.patch.object(subprocess, "run", recorder(calls, lambda argv: 1)), redirect_stderr(err):
        w = make_worker()
        try:
            w.must(["false-step"], describe="the step")
            stopped = None
        except worker.Stop as exc:
            stopped = exc.code
        check("must: a non-zero exit stops the worker, exit 1, the step named", stopped == 1 and "step failed: the step" in err.getvalue()
              and "nothing after it ran" in err.getvalue(), err.getvalue())
        err.truncate(0)
        err.seek(0)
        try:
            w.best_effort(["soft-step"])
            check("best_effort: a failure is a warning that names it, and the worker goes on",
                  "warning: soft-step failed; continuing" in err.getvalue(), err.getvalue())
        except worker.Stop:
            check("best_effort: a failure is a warning that names it, and the worker goes on", False, "it stopped")
        check("probe: the command's own status is the answer", w.probe(["x"]) == 1)
    for label, exc in (("a missing command", OSError("no such file")), ("a timeout", subprocess.TimeoutExpired("x", 1))):
        with mock.patch.object(subprocess, "run", recorder([], lambda argv, e=exc: e)):
            check(f"probe: {label} is 127 (absent), not success and not a traceback", make_worker().probe(["x"]) == 127)
    calls = []
    with mock.patch.object(subprocess, "run", recorder(calls)):
        make_worker().must(["ok-step"])
    check("must: a zero exit goes on", len(calls) == 1)

    print("prepare: the account steps, as argument lists")
    with tempfile.TemporaryDirectory() as etc:
        calls = []

        def absent(argv):
            return 2 if argv[0] == "getent" else 0
        with mock.patch.object(subprocess, "run", recorder(calls, absent, stop_at="persist_accounts.py")), redirect_stderr(io.StringIO()):
            w = make_worker(env={"AGENT_FABRIC_ETC": etc, "PATH": os.environ.get("PATH", "")})
            try:
                worker.prepare(w)
            except Reached:
                pass
        argvs = [c[0] for c in calls]
        check("useradd: the home made, bash the login shell, the role in the comment, the login last, under sudo -n",
              ["sudo", "-n", "useradd", "-m", "-s", "/bin/bash", "-c", "agent-fabric backend-dev", LOGIN] in argvs, str(argvs))
        home = f"/home/{LOGIN}"
        check("the home is made private (700) once the account exists", ["sudo", "-n", "chmod", "700", home] in argvs, str(argvs))
        check("…and that is before the account is persisted", argvs.index(["sudo", "-n", "chmod", "700", home]) < len(argvs) - 1)
        persist = argvs[-1]
        check("persist: the Python entry, on the pinned interpreter, isolated, as root, for the login",
              persist[:5] == ["sudo", "-n", worker.PY, "-I", os.path.join(HERE, "tools", "fabric", "provisioning", "persist_accounts.py")]
              and persist[-1] == LOGIN, str(persist))

    print("the published host keys")
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(f"{root}/runtime/provisioning")
        keys = "github.com ssh-ed25519 AAAAfixture\ngithub.com ssh-rsa AAAAother\n"
        with open(f"{root}/runtime/provisioning/github-host-keys", "w") as fh:
            fh.write(keys)
        calls = []

        def no_known_hosts(argv):
            return 1 if "cat" in argv else 0
        with mock.patch.object(subprocess, "run", recorder(calls, no_known_hosts)), redirect_stderr(io.StringIO()):
            w = make_worker(root=root)
            w.home = f"/home/{LOGIN}"
            worker.trust_github_host_keys(w)
        known = f"/home/{LOGIN}/.ssh/known_hosts"
        tee = [c for c in calls if "tee" in c[0]]
        check("known_hosts is appended to (tee -a), as the account, never rewritten",
              len(tee) == 1 and tee[0][0] == ["sudo", "-n", "-u", LOGIN, "tee", "-a", known], str(tee))
        check("…with the published keys on stdin", tee and tee[0][1].get("input") == keys, str(tee))
        check("…and then mode 600", ["sudo", "-n", "-u", LOGIN, "chmod", "600", known] in [c[0] for c in calls])

    print("test_provisioning_worker:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

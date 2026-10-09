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

    print("finish: a project's host-check is a probe")
    with tempfile.TemporaryDirectory() as root:
        hc = f"{root}/projects/demo/integration/provisioning"
        os.makedirs(hc)
        with open(f"{hc}/host-check.sh", "w") as fh:
            fh.write("#!/bin/sh\necho hello-from-check\nexit 3\n")
        os.chmod(f"{hc}/host-check.sh", 0o755)
        for label, answer in (("runs and its failing status is ignored", lambda argv: 0), ("cannot be started", lambda argv: OSError("x")),
                              ("times out", lambda argv: subprocess.TimeoutExpired("x", 1))):
            err = io.StringIO()
            real = subprocess.run

            def fake(argv, _answer=answer, **kw):
                if argv[:1] == ["bash"]:
                    out = _answer(argv)
                    if isinstance(out, BaseException):
                        raise out
                    return real(argv, **kw)
                if argv[:1] == ["getent"]:
                    return subprocess.CompletedProcess(argv, 2, stdout="", stderr="")
                raise Reached
            w = make_worker("--clone", "demo=git@h:o/demo.git", "--project", "demo", root=root)
            w.a.phase = "finish"
            with mock.patch.object(subprocess, "run", fake), redirect_stderr(err):
                try:
                    worker.finish(w)
                    reached = False
                except Reached:
                    reached = True       # past the check, at the first command of step 6
                except Exception as e:  # noqa: BLE001 - the case is that nothing else escapes
                    reached = repr(e)
            check(f"a host-check that {label}: the run goes on to step 6", reached is True, f"{reached} {err.getvalue()}")
            if label.startswith("runs"):
                check("…and its output is shown indented", "   hello-from-check" in err.getvalue(), err.getvalue())

    print("dry run: a step of two commands says it once")
    err = io.StringIO()
    with redirect_stderr(err):
        make_worker("--dry-run").must_as_login_seq([["a"], ["b"]], "the line")
    check("one would line", err.getvalue().count("would: as_login the line") == 1, err.getvalue())

    print("the read-backs and the download")
    seen: dict = {}

    def spy(argv, **kw):
        seen.update(kw, argv=list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="main\n", stderr=None)
    with mock.patch.object(subprocess, "run", spy):
        out = make_worker().as_login_out(["git", "x"])
    check("a read-back keeps stderr out of the value", out == "main\n" and seen.get("stderr") == subprocess.DEVNULL, str(seen))
    got: list = []

    def fetch(argv, **kw):
        got.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="#!/bin/sh\n", stderr="")
    with mock.patch.object(subprocess, "run", fetch):
        w = make_worker()
        worker.vendor_install(w, "https://example.invalid/install.sh", [])
    check("the download is not run in a login shell (a profile's stdout would become the vendor's script)",
          "curl" in got[0] and "-c" in got[0] and "-lc" not in got[0], str(got[0]))
    check("…while the vendor's script itself runs in one", "-lc" in got[1] and "bash" in got[1], str(got[1:]))
    with mock.patch.object(subprocess, "run", recorder([], lambda argv: OSError("gone"))), redirect_stderr(io.StringIO()) as e2:
        make_worker().best_effort(["soft"])
    check("best_effort: a command that cannot start is a warning too", "warning: soft failed; continuing" in e2.getvalue())

    print("test_provisioning_worker:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

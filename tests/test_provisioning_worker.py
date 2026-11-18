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
import json
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
        # The host's own fabric-python is machine state; the pin check has its cases below.
        with mock.patch.object(subprocess, "run", recorder(calls, absent, stop_at="persist_accounts.py")), \
                mock.patch.object(worker, "pin_problem", lambda root: None), redirect_stderr(io.StringIO()):
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

    print("prepare: the pin, not the host's python3 (ADR-040 rule 1)")
    import python_pin
    with tempfile.TemporaryDirectory() as etc, tempfile.TemporaryDirectory() as root:
        os.makedirs(f"{root}/runtime")
        with open(f"{root}/runtime/python.json", "w") as fh:
            fh.write(open(f"{HERE}/runtime/python.json").read())

        def prepared(problem, *, rt=root):
            calls = []
            err = io.StringIO()
            seen = []

            def fake_check(p, *a, **k):
                seen.append(p["python"])
                return problem
            with mock.patch.object(subprocess, "run", recorder(calls, lambda argv: 2 if argv[0] == "getent" else 0, stop_at="persist_accounts.py")), \
                    mock.patch.object(python_pin, "check", fake_check), redirect_stderr(err):
                w = make_worker(root=rt, env={"AGENT_FABRIC_ETC": etc, "PATH": os.environ.get("PATH", "")})
                try:
                    worker.prepare(w)
                    stopped = "ran"
                except worker.Stop as exc:
                    stopped = f"stop {exc.code}"
                except Reached:
                    stopped = "reached"
            return stopped, err.getvalue(), calls, seen
        stopped, text, calls, seen = prepared(None)
        check("the pinned build in place: prepare goes on to the account", stopped == "reached" and calls[0][0][:3] == ["getent", "passwd", LOGIN], f"{stopped}\n{text}")
        check("…and the build asked about is the one runtime/python.json under the root pins",
              seen == [json.load(open(f"{root}/runtime/python.json"))["python"]], str(seen))
        check("…and no call asks the host's python3 anything",
              not any(c[0][:1] == ["python3"] for c in calls), str([c[0] for c in calls]))
        stopped, text, calls, seen = prepared("/usr/local/bin/fabric-python is absent")
        check("fabric-python absent or another build: exit 1 before any account, naming the fact and python_pin.py install",
              stopped == "stop 1" and "is absent" in text and "python_pin.py install" in text and not any("sudo" in c[0] for c in calls), f"{stopped}\n{text}\n{calls}")
        for shape in ("[]", "null"):
            with tempfile.TemporaryDirectory() as odd:
                os.makedirs(f"{odd}/runtime")
                with open(f"{odd}/runtime/python.json", "w") as fh:
                    fh.write(shape)
                got = worker.pin_problem(odd)
                check(f"a pin file of {shape} is a one-line problem, not a traceback", bool(got) and "unreadable" in got, str(got))
        with tempfile.TemporaryDirectory() as bad:
            stopped, text, calls, seen = prepared(None, rt=bad)
            check("an unreadable pin is a stop, never a pass: the check is not asked at all",
                  stopped == "stop 1" and "runtime/python.json unreadable" in text and not any("sudo" in c[0] for c in calls) and seen == [], f"{stopped}\n{text}")

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

    print("finish: a project's Python probe is run with the pin, ahead of its script")
    with tempfile.TemporaryDirectory() as root:
        hc = f"{root}/projects/demo/integration/provisioning"
        os.makedirs(hc)
        for name in ("host_check.py", "host-check.sh"):
            with open(f"{hc}/{name}", "w") as fh:
                fh.write("#!/bin/sh\nexit 0\n")
            os.chmod(f"{hc}/{name}", 0o755)
        ran: list = []

        def fake_probe(argv, **kw):
            if argv[:1] == ["getent"]:
                return subprocess.CompletedProcess(argv, 2, stdout="", stderr="")
            if argv[:1] in (["bash"], [worker.PY]):
                ran.append(list(argv))
                return subprocess.CompletedProcess(argv, 0, stdout="line-from-probe\n", stderr="")
            raise Reached
        w = make_worker("--clone", "demo=git@h:o/demo.git", "--project", "demo", root=root)
        w.a.phase = "finish"
        err = io.StringIO()
        with mock.patch.object(subprocess, "run", fake_probe), redirect_stderr(err):
            try:
                worker.finish(w)
            except Reached:
                pass
        # Mutation: the script preferred over host_check.py leaves ran as [["bash", ...]].
        check("host_check.py beside host-check.sh: only the pinned Python runs, on the .py",
              ran != [] and all(r == [worker.PY, "-I", f"{hc}/host_check.py"] for r in ran), str(ran))
        check("…and its output is shown indented", "   line-from-probe" in err.getvalue(), err.getvalue())

    print("finish: a clone that is already there is pointed at its registry remote")
    ssh = "git@github.com:BlueTeam-OU/agent-fabric.git"
    https = "https://github.com/BlueTeam-OU/agent-fabric.git"

    def step6(origin: str | None, *argv: str, pushurl: str | None = None, as_project: bool = True, present: bool = True, earlier: str | None = None):
        """Run finish up to the end of step 6 with a present clone whose remote.origin.url reads `origin` (None: unreadable)."""
        seen: list = []

        def fake(cmd, **kw):
            seen.append(list(cmd))
            if cmd[:1] == ["getent"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")      # the account exists: its paths are asked about
            if worker.PATH_PROBE in cmd:
                # What `test -d` and `test -f` said before: the clone's .git a directory and the module a file, or nothing there.
                paths = cmd[cmd.index(worker.PATH_PROBE) + 1:]
                kind = lambda p: "absent" if not present else "dir" if p.endswith(".git") else "file"  # noqa: E731
                return subprocess.CompletedProcess(cmd, 0, stdout="".join(f"new-agent-path\t{i}\t{kind(p)}\n" for i, p in enumerate(paths)), stderr="")
            if "--get-regexp" in cmd:
                # One call answers both, as git does with --null: `key\nvalue\0`, only the keys that are set; none is status 1.
                found = [f"remote.origin.url\n{earlier}\0"] if earlier is not None else []
                found += [f"remote.origin.url\n{origin}\0"] if origin is not None else []
                found += [f"remote.origin.pushurl\n{pushurl}\0"] if pushurl is not None else []
                return subprocess.CompletedProcess(cmd, 0 if found else 1, stdout="".join(found), stderr=None)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        out = io.StringIO()
        w = make_worker(*(["--clone", f"agent-fabric={ssh}"] if as_project else []), *argv)
        w.a.phase = "finish"
        with mock.patch.object(subprocess, "run", fake), mock.patch.object(worker, "record_launch_provider", side_effect=Reached), \
                redirect_stderr(out):
            try:
                worker.finish(w)
            except Reached:
                pass
        return seen, out.getvalue()

    sets = lambda seen: [c for c in seen if "set-url" in c]  # noqa: E731
    seen, said = step6(https)
    check("an https origin is set to the registry's SSH remote, as the login, and said in one line",
          len(sets(seen)) == 1 and sets(seen)[0][-4:] == ["remote", "set-url", "origin", ssh] and f"6. agent-fabric: origin set to {ssh}" in said
          and f"-u {LOGIN}" in " ".join(sets(seen)[0]), f"{sets(seen)} {said}")
    seen, said = step6(ssh)
    check("a clone already on its remote is untouched", not sets(seen) and "origin set" not in said, f"{sets(seen)} {said}")
    seen, said = step6(https, "--dry-run")
    check("dry run says what it would do and changes nothing", not sets(seen) and f"would: as_login git -C ~/projects/'agent-fabric' remote set-url origin '{ssh}'" in said
          and "origin set to" not in said,
          f"{sets(seen)} {said}")
    seen, said = step6(https, "--project", "other")
    check("a project the registry gives no remote for is left alone", len(sets(seen)) == 1, f"{sets(seen)} {said}")
    seen, said = step6(ssh, pushurl=https)
    check("a push URL of its own is said, not rewritten", not sets(seen) and f"origin has its own push URL {https}" in said, f"{sets(seen)} {said}")
    seen, said = step6(https, pushurl=ssh)
    check("…and none is said when it is the registry remote", len(sets(seen)) == 1 and "push URL" not in said, f"{sets(seen)} {said}")
    seen, said = step6(https)
    check("origin and push URL are read in one call, not two",
          len([c for c in seen if "config" in c]) == 1 and not any("remote.origin.url" in c for c in seen), str(seen))
    seen, said = step6(ssh, earlier=https)
    check("two origin URLs: the last is the one, as --get reads it", not sets(seen), f"{sets(seen)} {said}")
    seen, said = step6(None, pushurl=https)
    check("a push URL with no origin is no answer: left as it is, and said", not sets(seen) and "origin not readable; left as it is" in said
          and "push URL" not in said, f"{sets(seen)} {said}")
    seen, said = step6(None)
    check("an origin that cannot be read is left as it is, and said", not sets(seen) and "origin not readable; left as it is" in said, f"{sets(seen)} {said}")

    print("finish: the fabric checkout of step 4 when agent-fabric is not a --project")
    seen, said = step6(https, "--fabric-remote", ssh, "--project", "other", as_project=False)
    check("its https origin is set to the registry's SSH remote, as the login, said in one line",
          [c[-4:] for c in sets(seen)] == [["remote", "set-url", "origin", ssh]] and f"6. agent-fabric: origin set to {ssh}" in said
          and "-C" in sets(seen)[0] and f"-u {LOGIN}" in " ".join(sets(seen)[0]), f"{sets(seen)} {said}")
    seen, said = step6(ssh, "--fabric-remote", ssh, as_project=False)
    check("…only if it differs", not sets(seen) and "origin set" not in said, f"{sets(seen)} {said}")
    seen, said = step6(https, "--fabric-remote", ssh, "--dry-run", as_project=False)
    check("…never in a dry run (said as would)", not sets(seen) and f"remote set-url origin '{ssh}'" in said and "origin set to" not in said,
          f"{sets(seen)} {said}")
    seen, said = step6(https, "--fabric-remote", ssh, "--dry-run", as_project=False, present=False)
    check("…and a dry run with no clone made yet reads nothing", not sets(seen) and "origin" not in said, f"{seen} {said}")
    seen, said = step6(https, as_project=False)
    check("without --fabric-remote the checkout is left as it is", not sets(seen), f"{sets(seen)} {said}")
    seen, said = step6(https, "--fabric-remote", ssh)
    check("when agent-fabric is also a --clone project, origin is set once, not twice", len(sets(seen)) == 1, f"{sets(seen)}")
    try:
        wa.parse_args(["finish", LOGIN, "--human", "--fabric-remote", ssh])
        refused = False
    except wa.Exit as exc:
        refused = exc.code == 2
    check("a human takes no --fabric-remote", refused)

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
    seen_shells: list = []

    def spy(argv, **kw):
        if "_" in argv:
            seen_shells.append((argv[argv.index("_") - 2], argv[argv.index("_") + 1:]))
        out = {worker.PATH_PROBE: "new-agent-path\t0\tdir\n",
               worker.FABRIC_UPDATE: "".join(f"new-agent-step\t{k}\t{v}\n" for k, v in
                                             (("branch", "main"), ("fetch", "0"), ("ahead", "0"), ("merge", "0"), ("sha", "abc1234"))),
               "--get-regexp": "remote.origin.url\ngit@x:y\0"}
        return subprocess.CompletedProcess(argv, 0, stdout=next((v for k, v in out.items() if k in argv), ""), stderr="")
    with mock.patch.object(subprocess, "run", spy):
        w = make_worker()
        w.home = "/home/x"
        worker.fabric_checkout(w)
        with redirect_stderr(io.StringIO()) as said_origin:
            worker.point_origin_at_registry(w, "p", "git@x:y")
    git_flags = {flag for flag, rest in seen_shells if "git" in rest}
    check("the fabric checkout's and the origin's git reads and writes all run in a login shell, one environment",
          git_flags == {"-lc"} and len(seen_shells) == 3 and "not readable" not in said_origin.getvalue(), str(seen_shells))
    seen_shells.clear()
    with mock.patch.object(subprocess, "run", spy):
        w = make_worker()
        w.as_login(["test", "-e", "/p"], login_shell=False)
        w.as_login(["claude", "--version"])
    check("a file test needs no profile; a tool keeps it",
          [f for f, _ in seen_shells] == ["-c", "-lc"], str(seen_shells))
    # Debian's /etc/profile assigns PATH outright for a non-root login, so the PATH env -i set is gone when the command runs: the script
    # re-asserts it. The profile here is the account's own, read by a real login shell through a sudo that only drops its flags.
    # (tests/test_new_agent_cli.py's sudo fake runs a plain shell, to spare the host's profile.d: this is where that is covered.)
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        os.makedirs(os.path.join(home, ".local", "bin"))
        with open(os.path.join(home, ".bash_profile"), "w", encoding="utf-8") as fh:
            fh.write("PATH=/usr/bin:/bin\n")
        with open(os.path.join(home, ".local", "bin", "account-only-tool"), "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\necho found\n")
        os.chmod(os.path.join(home, ".local", "bin", "account-only-tool"), 0o755)
        fake_sudo = os.path.join(tmp, "sudo")
        with open(fake_sudo, "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\n[ "$1" = -n ] && shift; [ "$1" = -u ] && shift 2; [ "$1" = -H ] && shift\nexec "$@"\n')
        os.chmod(fake_sudo, 0o755)
        w = make_worker()
        w.home, w.sudo = home, [fake_sudo]
        r = subprocess.run(w.as_login_argv(["account-only-tool"]), capture_output=True, text=True, timeout=60,
                           env={"PATH": "/usr/bin:/bin"})
    check("a profile that assigns PATH outright does not hide a tool the account's PATH names (the worker re-asserts PATH in its shell)",
          r.stdout == "found\n", f"{r.stdout!r} {r.stderr!r}")
    with mock.patch.object(subprocess, "run", recorder([], lambda argv: OSError("gone"))), redirect_stderr(io.StringIO()) as e2:
        make_worker().best_effort(["soft"])
    check("best_effort: a command that cannot start is a warning too", "warning: soft failed; continuing" in e2.getvalue())

    print("prepare: step 2 asks the account about its claude in one call, and a dangling link is not a claude")
    from provisioning import host_steps  # noqa: E402
    want = host_steps.claude_want(HERE, "")
    with tempfile.TemporaryDirectory() as tmp:
        fake_sudo = os.path.join(tmp, "sudo")
        with open(fake_sudo, "w", encoding="utf-8") as fh:      # drops its flags, logs what it was asked, runs it: real readlink and test
            fh.write(f'#!/bin/sh\n[ "$1" = -n ] && shift; [ "$1" = -u ] && shift 2; [ "$1" = -H ] && shift\n'
                     f'echo "$@" | grep -o "_ .*" >> {tmp}/asked\nexec "$@"\n')
        os.chmod(fake_sudo, 0o755)

        def step2(link_to: str | None, target_exists: bool) -> tuple[str, list[str]]:
            home = os.path.join(tmp, f"home-{link_to}-{target_exists}")
            os.makedirs(os.path.join(home, ".local", "bin"))
            if link_to:
                target = os.path.join(home, ".local", "share", "claude", "versions", link_to)
                os.makedirs(os.path.dirname(target))      # its directory is there either way: `readlink -f` answers for a missing last part
                if target_exists:
                    open(target, "w").close()
                os.symlink(target, os.path.join(home, ".local", "bin", "claude"))
            if os.path.exists(f"{tmp}/asked"):
                os.remove(f"{tmp}/asked")
            w = make_worker("--dry-run")
            w.home, w.sudo = home, [fake_sudo]
            err = io.StringIO()
            # The host's managed-settings drift is machine state, and it would refuse the install this case wants planned.
            with redirect_stderr(err), mock.patch.object(host_steps, "claude_install_refusal", lambda root, target: None):
                worker.install_claude_and_ori(w)
            asked = open(f"{tmp}/asked", encoding="utf-8").read().splitlines() if os.path.exists(f"{tmp}/asked") else []
            return err.getvalue(), [ln for ln in asked if ".local/bin/claude" in ln]
        # Mutation: `-e` read as `-f` (a dangling link answers with the path it would have, and is taken for the version).
        said, asked = step2(want, True)
        check("a link to the wanted version is present, said, after one question about it",
              f"2. claude {want} present" in said and len(asked) == 1, f"{said}{asked}")
        said, asked = step2(want, False)
        check("…a link to the wanted version that is not there is not a claude: the install is planned", f"2. claude {want} present" not in said
              and "would: as" in said and "install.sh" in said, said)
        said, asked = step2(None, False)
        check("…no link at all is asked once and the install planned", "would: as" in said and len(asked) == 1, f"{said}{asked}")

    print("j168: one question for many paths, as the account; an unknown is never an absent")
    with tempfile.TemporaryDirectory() as tmp:
        fake_sudo = os.path.join(tmp, "sudo")
        with open(fake_sudo, "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\nprintf "CALL %s\\n" "$*" >> ' + tmp + '/sudo.log\n[ "$1" = -n ] && shift; [ "$1" = -u ] && shift 2; [ "$1" = -H ] && shift\nexec "$@"\n')
        os.chmod(fake_sudo, 0o755)
        home = os.path.join(tmp, "home")
        os.makedirs(os.path.join(home, "d"))
        for name in ("d/f",):
            open(os.path.join(home, name), "w").close()
        os.symlink(os.path.join(home, "d"), os.path.join(home, "link-to-d"))
        w = make_worker()
        w.home, w.sudo = home, [fake_sudo]
        paths = [os.path.join(home, x) for x in ("d", "d/f", "nope", "d/f/under-a-file", "link-to-d")]
        with mock.patch.object(w, "account_exists", lambda: True):
            got = w.path_kinds(paths)
        check("a directory, a file, a missing path, a path under a file and a link to a directory, in ONE sudo call as the account",
              list(got.values()) == ["dir", "file", "absent", "absent", "dir"] and open(f"{tmp}/sudo.log").read().count("CALL ") == 1
              and open(f"{tmp}/sudo.log").read().startswith(f"CALL -n -u {LOGIN} -H env -i"), f"{got} {open(f'{tmp}/sudo.log').read()[:200]}")
        check("…and no sudo call at all for no paths", w.path_kinds([]) == {} and open(f"{tmp}/sudo.log").read().count("CALL ") == 1)
        # An account that does not exist (a dry run plans it) has no home: absent, without asking `sudo -u` of a login it does not know.
        with mock.patch.object(w, "account_exists", lambda: False), mock.patch.object(w, "as_login", side_effect=AssertionError("asked")):
            check("an account not made yet: everything absent, nothing run", w.path_kinds(paths[:2]) == dict.fromkeys(paths[:2], "absent"))
        if os.geteuid() != 0:
            # The control: the same child readable answers dir; unreadable, the answer is an error and never "absent".
            os.makedirs(os.path.join(home, "locked", "child"))
            with mock.patch.object(w, "account_exists", lambda: True):
                check("(control) a child of a readable directory is a directory", w.path_kinds([os.path.join(home, "locked", "child")]) ==
                      {os.path.join(home, "locked", "child"): "dir"})
                os.chmod(os.path.join(home, "locked"), 0)
                try:
                    err = io.StringIO()
                    try:
                        with redirect_stderr(err):
                            w.path_kinds([os.path.join(home, "locked", "child")])
                        stopped = None
                    except worker.Stop as exc:
                        stopped = exc.code
                finally:
                    os.chmod(os.path.join(home, "locked"), 0o700)
            check("a path the account cannot stat stops the run, naming the step: not read as absent",
                  stopped == 1 and "step failed: could not read 1 path(s)" in err.getvalue() and "nothing after it ran" in err.getvalue()
                  and os.path.join(home, "locked", "child") in err.getvalue() and "Permission denied" in err.getvalue(), err.getvalue())
    for label, stdout, rc in (("no answer at all", "", 0), ("a kind for only one of two paths", "new-agent-path\t0\tdir\n", 0),
                              ("a repeated index", "new-agent-path\t0\tdir\nnew-agent-path\t0\tdir\n", 0),
                              ("an unknown kind", "new-agent-path\t0\tdir\nnew-agent-path\t1\tmaybe\n", 0),
                              ("a tag line of the wrong shape", "new-agent-path\t0\tdir\textra\nnew-agent-path\t1\tdir\n", 0),
                              ("a full answer behind a non-zero exit", "new-agent-path\t0\tdir\nnew-agent-path\t1\tdir\n", 1)):
        w = make_worker()
        err = io.StringIO()
        with mock.patch.object(w, "account_exists", lambda: True), mock.patch.object(
                w, "as_login", lambda *a, _o=stdout, _r=rc, **k: subprocess.CompletedProcess(a, _r, _o, None)), redirect_stderr(err):
            try:
                w.path_kinds(["/a", "/b"])
                stopped = None
            except worker.Stop as exc:
                stopped = exc.code
        check(f"the probe's answer is refused, not read as a pass: {label}", stopped == 1 and "step failed: could not read 2 path(s)" in err.getvalue(),
              err.getvalue())
    w = make_worker()
    with mock.patch.object(w, "account_exists", lambda: True), mock.patch.object(
            w, "as_login", lambda *a, **k: subprocess.CompletedProcess(a, 0, "profile noise\nnew-agent-path\t0\tdir\nmore\nnew-agent-path\t1\tfile\n", None)):
        check("(control) a profile's own lines around the tag lines are ignored", w.path_kinds(["/a", "/b"]) == {"/a": "dir", "/b": "file"})

    # A project named twice is one project: its clone and its install are asked about once, before either is made.
    seen_paths: list = []

    def dup_fake(cmd, **kw):
        if cmd[:1] == ["getent"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if worker.PATH_PROBE in cmd:
            seen_paths.append(cmd[cmd.index(worker.PATH_PROBE) + 1:])
            return subprocess.CompletedProcess(cmd, 0, stdout="".join(f"new-agent-path\t{i}\tabsent\n" for i in range(len(seen_paths[-1]))), stderr="")
        raise Reached
    w = make_worker("--clone", "demo=git@h:o/demo.git", "--project", "demo", "--project", "demo")
    w.a.phase = "finish"
    with mock.patch.object(subprocess, "run", dup_fake), redirect_stderr(io.StringIO()):
        try:
            worker.finish(w)
        except Reached:
            pass
    check("a project named twice is asked about once: one .git path, the list without the repeat", w.a.projects == ["demo"]
          and len(seen_paths) == 1 and len(seen_paths[0]) == 1, f"{w.a.projects} {seen_paths}")

    print("j168: step 4 in one login shell, each check keeping its failure class")

    def step4(tags: list[tuple[str, str]], *argv: str, raw: str | None = None) -> tuple[int | None, str, list]:
        w = make_worker(*argv)
        w.home = "/home/x"
        runs: list = []
        err = io.StringIO()

        def fake_as_login(a, **k):
            runs.append(list(a))
            text = raw if raw is not None else "".join(f"new-agent-step\t{n}\t{v}\n" for n, v in tags)
            return subprocess.CompletedProcess(a, 0, text, None)
        with mock.patch.object(w, "path_kinds", lambda ps: dict.fromkeys(ps, "dir")), mock.patch.object(w, "as_login", fake_as_login), redirect_stderr(err):
            try:
                worker.fabric_checkout(w)
                stopped = None
            except worker.Stop as exc:
                stopped = exc.code
        return stopped, err.getvalue(), runs
    good = [("branch", "main"), ("fetch", "0"), ("ahead", "0"), ("merge", "0"), ("sha", "abc1234")]
    stopped, said, runs = step4(good)
    check("an up-to-date checkout: ONE as_login for the five git commands, said with the commit",
          stopped is None and len(runs) == 1 and "4. ~/projects/agent-fabric at origin/main (abc1234)" in said, f"{stopped} {said} {runs}")
    stopped, said, runs = step4(good[:1], "--dry-run")
    check("a dry run reads the branch only and says the fetch and the merge as would", stopped is None and len(runs) == 1
          and "would: as_login timeout 60 git -C ~/projects/agent-fabric fetch -q origin main" in said
          and "would: as_login git -C ~/projects/agent-fabric merge -q --ff-only origin/main" in said and runs[0][-1] == "dry", said)
    for label, tags, why in (
            ("a branch other than main", [("branch", "topic")], "is on topic, not main"),
            ("a detached HEAD", [("branch", "")], "is on a detached HEAD, not main"),
            ("a fetch that failed", [("branch", "main"), ("fetch", "1")], "step failed: as_login timeout 60 git -C ~/projects/agent-fabric fetch"),
            ("commits not on origin/main", [("branch", "main"), ("fetch", "0"), ("ahead", "2")], "has 2 commit(s) not on origin/main"),
            ("a count git could not give", [("branch", "main"), ("fetch", "0"), ("ahead", "")], "has an unknown number of commit(s)"),
            ("a merge that failed", [("branch", "main"), ("fetch", "0"), ("ahead", "0"), ("merge", "1")], "step failed: as_login git -C ~/projects/agent-fabric merge")):
        stopped, said, _ = step4(tags)
        check(f"{label}: the run stops, nothing after it", stopped == 1 and why in said and "4. ~/projects/agent-fabric at" not in said, said)
    for label, tags in (("no tag line at all", []), ("the fetch's tag missing", good[:1]), ("the count's tag missing", good[:2]),
                        ("the merge's tag missing", good[:3]), ("the commit's tag missing", good[:4])):
        stopped, said, _ = step4(tags)
        check(f"a script that stopped short is no pass: {label}", stopped == 1 and "step failed" in said and "at origin/main" not in said, said)
    stopped, said, _ = step4([], raw="new-agent-step\tbranch\tmain\nnew-agent-step\tbranch\tmain\n")
    check("a repeated tag is no answer", stopped == 1 and "could not be read" in said, said)
    stopped, said, _ = step4([], raw="profile\n" + "".join(f"new-agent-step\t{n}\t{v}\n" for n, v in good))
    check("(control) a profile's line before the tags is ignored", stopped is None and "(abc1234)" in said, said)
    # The script itself, against real git: an origin with one commit more than the clone, the clone on main, then not.
    with tempfile.TemporaryDirectory() as tmp:
        genv = {"PATH": os.environ["PATH"], "HOME": tmp, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}

        def git(*a: str, cwd: str = tmp) -> str:
            return subprocess.run(["git", "-c", "init.defaultBranch=main", *a], cwd=cwd, env=genv, text=True, capture_output=True, timeout=60, check=True).stdout.strip()

        def script(repo: str, mode: str = "real") -> dict[str, str]:
            out = subprocess.run(["bash", "-c", worker.FABRIC_UPDATE, "_", repo, mode], env=genv, text=True, capture_output=True, timeout=120)
            return worker.parse_tags(out.stdout, "step")
        git("init", "-q", "--bare", "origin.git")
        git("clone", "-q", "origin.git", "clone")
        open(f"{tmp}/clone/a", "w").close()
        git("add", "a", cwd=f"{tmp}/clone")
        git("commit", "-qm", "one", cwd=f"{tmp}/clone")
        git("push", "-q", "origin", "main", cwd=f"{tmp}/clone")
        git("clone", "-q", "origin.git", "second")
        open(f"{tmp}/second/b", "w").close()
        git("add", "b", cwd=f"{tmp}/second")
        git("commit", "-qm", "two", cwd=f"{tmp}/second")
        git("push", "-q", "origin", "main", cwd=f"{tmp}/second")
        tags = script(f"{tmp}/clone")
        check("the script, on real git: fetch, ahead 0, fast-forward merge, then the new commit's short name",
              tags == {"branch": "main", "fetch": "0", "ahead": "0", "merge": "0", "sha": git("rev-parse", "--short", "HEAD", cwd=f"{tmp}/clone")}
              and os.path.exists(f"{tmp}/clone/b"), str(tags))
        check("…a dry run changes nothing and reports only the branch", script(f"{tmp}/clone", "dry") == {"branch": "main"})
        open(f"{tmp}/clone/c", "w").close()
        git("add", "c", cwd=f"{tmp}/clone")
        git("commit", "-qm", "local", cwd=f"{tmp}/clone")
        tags = script(f"{tmp}/clone")
        check("…a local commit is counted and stops before the merge", tags.get("ahead") == "1" and "merge" not in tags, str(tags))
        git("checkout", "-qb", "topic", cwd=f"{tmp}/clone")
        check("…off main it stops at the branch", script(f"{tmp}/clone") == {"branch": "topic"})
        check("…a path that is no repository: an empty branch, nothing more", script(f"{tmp}/nowhere") == {"branch": ""})
        git("checkout", "-q", "main", cwd=f"{tmp}/clone")
        git("remote", "set-url", "origin", f"{tmp}/gone.git", cwd=f"{tmp}/clone")
        tags = script(f"{tmp}/clone")
        check("…an unreachable origin: the fetch's own status, and nothing after it", tags.get("fetch") not in (None, "0") and "ahead" not in tags, str(tags))

    print("test_provisioning_worker:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

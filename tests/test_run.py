#!/usr/bin/env python3
"""tests/run.py and tests/static.py through their command lines, in scratch trees with fake suites: the section argument,
the run's own TMPDIR and environment, the leak report, the count of failed suites, the exit codes, the end of a run that
is signalled (TERM: exit 143 and nothing left; KILL: the watcher removes the directory), and the static checks'
findings. The oracle for the port of tests/run.sh and tests/static.sh is the contract their headers state and the
bash test tests/test_leak-check.sh (its run.sh cases, run against a forwarder). Plain script: ok/FAIL, exit 1 on any
failure."""
from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
fails = 0
# Every process this run starts carries this token in its environment (env() sets it; nothing on the way drops it), and
# the cases that look in /proc for their own processes match it: two runs of this file at once on one account (one inside
# a `tests/run.sh python`, one beside it) found each other's sleeps by command line, counted them as survivors and killed
# them — an escaped daemon killed by the other run closed its pipe early and failed the daemon case.
RUN_TOKEN_VARIABLE = "TEST_RUN_PY_TOKEN"
RUN_TOKEN = uuid.uuid4().hex


capture: list | None = None   # a case that judges check()'s own calls sets it: they are recorded, not counted


def check(label: str, good: bool, detail: object = "") -> None:
    global fails
    if capture is not None:
        capture.append((label, good))
        return
    print(f"  {'ok  ' if good else 'FAIL'} {label}", flush=True)
    if not good:
        fails += 1
        if detail != "":
            print("      " + str(detail).replace("\n", "\n      "))


def write(path: str, text: str, mode: int = 0o644) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, mode)


def tree(base: str, files: dict[str, str] | None = None, scripts: dict[str, str] | None = None, lease: bool = False) -> str:
    """A git tree holding the runner, the static checks, the python suites' runner, quiet stand-ins for the corpus lint
    and the routing check, and `files` (tests/test_*.py fakes, or anything) and `scripts` (executable); with `lease`,
    tools/fabric/lease.py, which a full run imports to take its lease (kept out of the others: the static cases count
    and lint what a tree holds)."""
    os.makedirs(os.path.join(base, "tests"))
    for name in ("run.py", "static.py", "run_python_suites.py"):
        shutil.copy(os.path.join(TESTS, name), os.path.join(base, "tests", name))
    if lease:
        os.makedirs(os.path.join(base, "tools", "fabric"))
        shutil.copy(os.path.join(ROOT, "tools", "fabric", "lease.py"), os.path.join(base, "tools", "fabric", "lease.py"))
    write(os.path.join(base, "tools/fabric/lint.py"), "pass\n")
    write(os.path.join(base, "tools/fabric/routing.py"), "pass\n")
    write(os.path.join(base, "runtime/provisioning/github-host-keys.fingerprints"), "")
    for name, text in (files or {}).items():
        write(os.path.join(base, name), text)
    for name, text in (scripts or {}).items():
        write(os.path.join(base, name), text, 0o755)
    for argv in (["init", "-q", "-b", "main"], ["add", "-A"]):
        subprocess.run(["git", "-C", base, *argv], check=True, capture_output=True, env=env(base))
    return base


def env(base: str, **extra: str) -> dict[str, str]:
    """Nothing of the session's: not its TMPDIR, its credentials, its git or its locale."""
    runtime = os.path.join(os.path.dirname(base), "runtime")
    os.makedirs(runtime, exist_ok=True)
    e = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.path.join(os.path.dirname(base), "home"),
         "XDG_RUNTIME_DIR": runtime, "TMPDIR": "/nonexistent-session-tmpdir", "LANG": "C.UTF-8",
         "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
         "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "PYTHONDONTWRITEBYTECODE": "1",
         "AGENT_FABRIC_TEST_JOBS": "2",
         # Without this every full run these cases make would queue for the host's REAL full-suite lease behind the
         # fleet. The lease cases below turn it back on, each in a lease directory of its own.
         "AGENT_FABRIC_SUITE_LEASE": "0", RUN_TOKEN_VARIABLE: RUN_TOKEN}
    e.update(extra)
    return e


def ours(needle: bytes) -> list[int]:
    """This run's live processes (zombies excluded) whose command line holds `needle`. Another account's environment
    cannot be read, and is not ours."""
    mark = f"{RUN_TOKEN_VARIABLE}={RUN_TOKEN}".encode()
    found = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/cmdline", "rb") as fh:
                if needle not in fh.read():
                    continue
            with open(f"/proc/{name}/environ", "rb") as fh:
                if mark not in fh.read().split(b"\0"):
                    continue
            with open(f"/proc/{name}/stat", "rb") as fh:
                if fh.read().rsplit(b")", 1)[1].split()[0] == b"Z":
                    continue
        except (OSError, IndexError):
            continue
        found.append(int(name))
    return found


def run(base: str, *args: str, **extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, os.path.join(base, "tests", "run.py"), *args], cwd=base, env=env(base, **extra),
                          capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)


def runs_left(base: str) -> list[str]:
    return [n for n in os.listdir(os.path.join(os.path.dirname(base), "runtime")) if n.startswith("af-t.")]


def end_run(p: subprocess.Popen, own_group: bool) -> None:
    """Ends a run whose case cannot go on. A run started as a session leader (`own_group`) is a group of its own and is KILLed
    whole, also when its leader has already exited: the group id stays its own while any member lives, so no pid is probed.
    One that shares this test's group is asked to stop (TERM) while it runs, and ends its own tree and removes its directory."""
    try:
        if own_group:
            os.killpg(p.pid, signal.SIGKILL)
        elif p.returncode is None:
            p.terminate()
    except OSError:
        pass
    # Bounded: an orphan that holds the run's pipe would otherwise hold this call too.
    try:
        p.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        p.kill()
        try:
            p.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            pass


def wait_until(p: subprocess.Popen, ready, what: str, timeout: float = 120.0, own_group: bool = False) -> bool:
    """Polls `ready` until it holds, with the run `p` still alive. A case that signals a run must signal it in the state the
    case describes, so the wait has no ceiling a loaded machine reaches (10 s once passed with no suite started: the signal
    then went to a run that had nothing to show, exit 129 and no output). When the state is not reached, because the run
    ended first or the deadline passed, the run is ended and the one failure says so; the caller skips the rest of the case,
    so no assertion reports a behaviour that was never exercised."""
    deadline = time.monotonic() + timeout
    while not ready():
        if p.poll() is not None:
            why = f"the run exited ({p.returncode}) before {what}"
        elif time.monotonic() > deadline:
            why = f"{what} did not happen within {timeout:g} s"
        else:
            time.sleep(0.1)
            continue
        end_run(p, own_group)
        check(f"precondition: {why}", False)
        return False
    return True


def poll_until(ready, timeout: float) -> bool:
    """What a case observes after its signal (no precondition): True once `ready` holds, False at the deadline."""
    deadline = time.monotonic() + timeout
    while not ready():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.1)
    return True


def suite(body: str) -> str:
    return "import os, sys\n" + body


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="test_run.") as sandbox:
        n = 0

        def fresh(**kw) -> str:
            nonlocal n
            n += 1
            return tree(os.path.join(sandbox, f"t{n}", "repo"), **kw)

        print("the section argument")
        base = fresh(files={"tests/test_a.py": suite("print('RAN-A')\n")})
        for args in (["bogus"], ["all", "extra"], ["--static"]):
            r = run(base, *args)
            check(f"{args}: exit 2, said on stderr, nothing run and no directory made",
                  r.returncode == 2 and "no section" in r.stderr and "(all, static, python, bash)" in r.stderr
                  and "RAN-A" not in r.stdout and not runs_left(base), (r.returncode, r.stderr, r.stdout))

        print("the python section: the suites' count, the lint and the routing check")
        base = fresh(files={"tests/test_ok.py": suite("print('fine')\n"),
                            "tests/test_bad.py": suite("print('broken')\nsys.exit(3)\n")})
        r = run(base, "python")
        check("one failing suite among passing: exit 1, FAILED_SUITES=1 from the runner, the run counts it",
              r.returncode == 1 and "FAILED_SUITES=1" in r.stdout and "tests/run.py: 1 suite(s) FAILED" in r.stdout
              and "== tests/test_bad.py" in r.stdout and "== corpus lint" in r.stdout and "== routing check" in r.stdout,
              (r.returncode, r.stdout, r.stderr))
        check("…the last line is the count of failed suites", r.stdout.rstrip().rsplit("\n", 1)[-1] == "tests/run.py: 1 suite(s) FAILED",
              r.stdout[-200:])
        base = fresh(files={"tests/test_ok.py": suite("print('fine')\n")})
        r = run(base, "python")
        check("all passing: exit 0, FAILED_SUITES=0, no failure line, and the run says so last",
              r.returncode == 0 and "FAILED_SUITES=0" in r.stdout and "FAILED" not in r.stdout.replace("FAILED_SUITES", "")
              and r.stdout.rstrip().rsplit("\n", 1)[-1] == "tests/run.py: all suites passed",
              (r.returncode, r.stdout))
        base = fresh(files={"tests/test_ok.py": suite("print('fine')\n")})
        write(os.path.join(base, "tools/fabric/lint.py"), "import sys\nprint('lint finding')\nsys.exit(1)\n")
        r = run(base, "python")
        check("the corpus lint failing counts as a failed suite, though every python suite passed",
              r.returncode == 1 and "tests/run.py: 1 suite(s) FAILED" in r.stdout and "lint finding" in r.stdout, r.stdout)
        base = fresh(files={"tests/test_ok.py": suite("print('fine')\n")})
        os.remove(os.path.join(base, "tools/fabric/routing.py"))
        r = run(base, "python")
        check("a check whose file is missing is a failed suite, never skipped", r.returncode == 1
              and "tests/run.py: 1 suite(s) FAILED" in r.stdout, (r.returncode, r.stdout, r.stderr))

        print("through the forwarders tests/run.sh and tests/static.sh, which CI and every habit call")

        def via(base: str, script: str, *args: str, **extra: str) -> subprocess.CompletedProcess:
            # Copied in untracked, so the tree's count of bash scripts stays what the cases above state.
            shutil.copy(os.path.join(TESTS, script), os.path.join(base, "tests", script))
            return subprocess.run(["bash", os.path.join(base, "tests", script), *args], cwd=base, env=env(base, **extra),
                                  capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)

        base = fresh(files={"tests/test_ok.py": suite("print('RAN', os.environ.get('AGENT_FABRIC_RUNNER'))\n")})
        r = via(base, "run.sh", "python")
        check("run.sh python: the run says so last under run.sh's own name, exit 0, and no suite sees the variable",
              r.returncode == 0 and r.stdout.rstrip().rsplit("\n", 1)[-1] == "tests/run.sh: all suites passed" and "RAN None" in r.stdout,
              (r.returncode, r.stdout[-300:], r.stderr))
        base = fresh(files={"tests/test_bad.py": suite("sys.exit(3)\n")})
        r = via(base, "run.sh", "python")
        check("…a failing suite: exit 1 and `tests/run.sh: 1 suite(s) FAILED` last",
              r.returncode == 1 and r.stdout.rstrip().rsplit("\n", 1)[-1] == "tests/run.sh: 1 suite(s) FAILED", (r.returncode, r.stdout[-300:]))
        r = via(base, "run.sh", "bogus")
        check("…a misspelt section: exit 2 and run.sh says so on stderr, nothing made",
              r.returncode == 2 and r.stderr.startswith("tests/run.sh: no section 'bogus'") and not runs_left(base), (r.returncode, r.stderr))
        r = run(base, "bogus", AGENT_FABRIC_RUNNER="something else")
        check("run.py itself keeps its own name, and a runner name that is not the forwarder's is ignored",
              r.returncode == 2 and r.stderr.startswith("tests/run.py: no section"), r.stderr)
        base = fresh(scripts={"good.sh": "#!/usr/bin/env bash\necho fine\n"})
        r = via(base, "static.sh")
        check("static.sh: the static checks' own output and exit status", r.returncode == 0 and "static: 1 bash script(s)\n" in r.stdout
              and r.stdout.rstrip().rsplit("\n", 1)[-1].startswith(("static: all bash scripts parse", "static: passed, but NOT run here")),
              (r.returncode, r.stdout, r.stderr))

        print("the run's own environment and directory")
        base = fresh(files={"tests/test_env.py": suite(
            "import json\n"
            "keys = ['TMPDIR', 'PYTHONUNBUFFERED', 'GZCOORD_DEFAULT_LOCALE_ONLY', 'GIT_CONFIG_COUNT', 'GIT_CONFIG_KEY_0',\n"
            "        'GIT_CONFIG_VALUE_0', 'GIT_CONFIG_KEY_1', 'GIT_CONFIG_VALUE_1']\n"
            "print('ENV ' + json.dumps({k: os.environ.get(k) for k in keys}))\n"
            "print('TMPDIR-EXISTS ' + str(os.path.isdir(os.environ['TMPDIR'])))\n")})
        r = run(base, "python")
        import json
        line = next((ln for ln in r.stdout.splitlines() if ln.startswith("ENV ")), "ENV {}")
        got = json.loads(line[4:])
        runtime = os.path.join(os.path.dirname(base), "runtime")
        check("TMPDIR is a fresh af-t.* directory under XDG_RUNTIME_DIR, not the session's",
              (got.get("TMPDIR") or "").startswith(os.path.join(runtime, "af-t.")), got)
        check("…it existed while the suite ran", "TMPDIR-EXISTS True" in r.stdout, r.stdout)
        check("…and is gone when the run ends", not runs_left(base), os.listdir(runtime))
        check("unbuffered output, the default locale pinned, git signing off in the environment",
              got.get("PYTHONUNBUFFERED") == "1" and got.get("GZCOORD_DEFAULT_LOCALE_ONLY") == "1"
              and got.get("GIT_CONFIG_COUNT") == "2" and (got.get("GIT_CONFIG_KEY_0"), got.get("GIT_CONFIG_VALUE_0")) == ("commit.gpgsign", "false")
              and (got.get("GIT_CONFIG_KEY_1"), got.get("GIT_CONFIG_VALUE_1")) == ("tag.gpgsign", "false"), got)
        r = subprocess.run([sys.executable, os.path.join(base, "tests", "run.py"), "python"], cwd=base, capture_output=True, text=True,
                           env=env(base, XDG_RUNTIME_DIR="/nonexistent-runtime"), timeout=120)
        line = next((ln for ln in r.stdout.splitlines() if ln.startswith("ENV ")), "ENV {}")
        check("no usable XDG_RUNTIME_DIR: /tmp is the fallback", (json.loads(line[4:]).get("TMPDIR") or "").startswith("/tmp/af-t."), line)

        print("a suite that leaves something behind is a failure, named")
        base = fresh(files={
            "tests/test_leaves.py": suite("for name in ('a b', 'star*.py', 'plain'):\n"
                                          "    open(os.path.join(os.environ['TMPDIR'], name), 'w').close()\n"),
            "tests/test_tidy.py": suite("import tempfile\n"
                                        "with tempfile.TemporaryDirectory() as d:\n    open(os.path.join(d, 'x'), 'w').close()\n")})
        r = run(base, "python")
        check("the report names each entry whole, indented, and the run fails",
              r.returncode == 1 and "== scratch left behind under " in r.stdout
              and "\n   a b\n" in r.stdout and "\n   star*.py\n" in r.stdout and "\n   plain\n" in r.stdout
              and "tests/run.py: 1 suite(s) FAILED" in r.stdout, (r.returncode, r.stdout))
        check("…the leaked directory is removed anyway", not runs_left(base), os.listdir(runtime))
        base = fresh(files={"tests/test_tidy.py": suite("import tempfile\n"
                                                        "with tempfile.TemporaryDirectory() as d:\n    open(os.path.join(d, 'x'), 'w').close()\n")})
        r = run(base, "python")
        check("positive control: a suite that cleans up after itself is no leak", r.returncode == 0 and "scratch left behind" not in r.stdout,
              (r.returncode, r.stdout))

        print("the static section")
        base = fresh(scripts={"good.sh": "#!/usr/bin/env bash\necho fine\n", "tool": "#!/bin/bash\necho fine\n"})
        r = run(base, "static")
        check("clean scripts: exit 0, the header and the count of bash scripts", r.returncode == 0
              and "== static (bash -n, shellcheck, ruff)" in r.stdout and "static: 2 bash script(s)" in r.stdout, (r.returncode, r.stdout, r.stderr))
        base = fresh(scripts={"bad.sh": "#!/usr/bin/env bash\nif then fi (\n"})
        r = run(base, "static")
        check("a script that does not parse: ✗ bash -n <file>, static: FAILED, exit 1",
              r.returncode == 1 and "✗ bash -n bad.sh" in r.stdout and "static: FAILED" in r.stdout
              and "tests/run.py: 1 suite(s) FAILED" in r.stdout, (r.returncode, r.stdout, r.stderr))
        base = fresh(scripts={"dash.sh": "#!/bin/sh\necho x\n"})
        r = run(base, "static")
        check("a #!/bin/sh script is refused, named", r.returncode == 1 and "dash.sh" in r.stdout
              and "the repository's scripts are bash" in r.stdout, r.stdout)
        base = fresh(files={"broken.py": "def f(:\n"})
        r = run(base, "static")
        check("a Python file that does not compile is named", r.returncode == 1 and "✗ py_compile broken.py" in r.stdout, r.stdout)
        check("…and compiling it wrote no bytecode into the tree",
              not os.path.isdir(os.path.join(base, "__pycache__")), os.listdir(base))
        base = fresh(files={"runtime/provisioning/x.sh": "#!/usr/bin/env bash\nssh-keyscan github.com\n"})
        r = run(base, "static")
        check("ssh-keyscan in provisioning is refused", r.returncode == 1 and "ssh-keyscan in provisioning" in r.stdout, r.stdout)
        base = fresh(files={"runtime/provisioning/y.sh": "#!/usr/bin/env bash\n# never ssh-keyscan\n"})
        r = run(base, "static")
        check("positive control: a comment that names it is no finding", r.returncode == 0, r.stdout)
        base = fresh(files={"m.mjs": "const u = new URL('./a', import.meta.url);\nconst p = u.pathname;\n"})
        r = run(base, "static")
        check("a module URL reaching the filesystem as .pathname is refused",
              r.returncode == 1 and "m.mjs:2:" in r.stdout and "fileURLToPath" in r.stdout, r.stdout)
        fake = os.path.join(sandbox, "fakebin")
        write(os.path.join(fake, "shellcheck"), "#!/usr/bin/env bash\necho 'fake shellcheck finding'\nexit 1\n", 0o755)
        base = fresh(scripts={"good.sh": "#!/usr/bin/env bash\necho fine\n"})
        r = subprocess.run([sys.executable, os.path.join(base, "tests", "run.py"), "static"], cwd=base, capture_output=True, text=True,
                           env=env(base, PATH=f"{fake}:{os.environ.get('PATH', '')}"), timeout=120)
        check("shellcheck's findings fail the run", r.returncode == 1 and "fake shellcheck finding" in r.stdout, (r.returncode, r.stdout))
        minbin = os.path.join(sandbox, "minbin")
        os.makedirs(minbin)
        for tool_name in ("bash", "git"):
            os.symlink(shutil.which(tool_name) or f"/usr/bin/{tool_name}", os.path.join(minbin, tool_name))
        r = subprocess.run([sys.executable, os.path.join(base, "tests", "static.py")], cwd=base, capture_output=True, text=True,
                           env=env(base, PATH=minbin), timeout=120)
        check("a missing tool is said, and the last line names what did not run on this host",
              r.returncode == 0 and "shellcheck not installed" in r.stdout
              and r.stdout.rstrip().rsplit("\n", 1)[-1] == "static: passed, but NOT run here: shellcheck ruff (CI runs it)", (r.returncode, r.stdout))

        print("the bash section: the table, each suite's own environment, a command that cannot start")
        base = fresh(files={"tests/placeholder": ""})
        script = (
            "import sys\nsys.path.insert(0, 'tests')\nimport run\n"
            "run.BASH_SUITES[:] = [('first', {}, ['true']), ('second', {'PROBE': '7'}, ['sh', '-c', 'test \"$PROBE\" = 7 && echo SAW-PROBE']),\n"
            "                      ('third', {}, ['false']), ('fourth', {}, ['/nonexistent/command'])]\n"
            "sys.exit(run.main(['bash']))\n")
        r = subprocess.run([sys.executable, "-c", script], cwd=base, env=env(base), capture_output=True, text=True, timeout=60)
        check("the suites run in order under their labels, each with its own extra environment",
              r.stdout.index("== first") < r.stdout.index("== second") < r.stdout.index("== third") and "SAW-PROBE" in r.stdout, r.stdout)
        check("a failing and an unstartable command are both counted, the unstartable one named on stderr",
              r.returncode == 1 and "tests/run.py: 2 suite(s) FAILED" in r.stdout and "/nonexistent/command could not be started" in r.stderr,
              (r.returncode, r.stdout, r.stderr))

        print("a case whose run never reaches the state it signals in reports that, once, and ends the run")
        # wait_until reports through check(), which would fail this file: its calls are captured here, and judged below.
        global capture
        seen: list = []
        capture = seen
        try:
            gone_at = subprocess.Popen([sys.executable, "-c", "pass"], stdin=subprocess.DEVNULL)
            began = time.monotonic()
            r_exit = wait_until(gone_at, lambda: False, "its suites started", timeout=60.0)
            took_exit = time.monotonic() - began
            seen_exit, seen[:] = list(seen), []
            results = []
            childpid = os.path.join(sandbox, "hung-child.pid")
            for new_session in (False, True):
                # A shell holding a child of its own: ended with its group when it leads one, so the child goes with it.
                hung = subprocess.Popen(["sh", "-c", f"sleep 60 & echo $! > {childpid}; wait"], stdin=subprocess.DEVNULL,
                                        start_new_session=new_session)
                poll_until(lambda: os.path.exists(childpid) and open(childpid).read().strip() != "", 30.0)
                child = int(open(childpid).read())
                results.append((wait_until(hung, lambda: False, "its suites started", timeout=1.0, own_group=new_session), list(seen), hung.poll()))
                seen[:] = []
                # Not "alive": a killed child stays a zombie until its parent is reaped.
                dead = poll_until(lambda: not os.path.exists(f"/proc/{child}")
                                  or open(f"/proc/{child}/stat").read().rsplit(")", 1)[1].split()[0] == "Z", 10.0)
                results[-1] += (dead if new_session else True,)
                if not new_session:
                    os.kill(child, signal.SIGKILL)     # the shell was only asked to stop; its child holds this file's stdout
                os.unlink(childpid)
            alive = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdin=subprocess.DEVNULL)
            ok_state = wait_until(alive, lambda: True, "its suites started")
            seen_ok, seen[:] = list(seen), []
            left_running = alive.poll() is None
            alive.kill()
            alive.wait()
        finally:
            capture = None
        # Kills: dropping the p.poll() test (the run that has already exited would be waited on for the whole 60 s, then
        # reported as a deadline) and reporting through the behaviour's own label.
        check("a run that exited before the state: reported at once as an exit, once, not after the deadline",
              r_exit is False and took_exit < 30 and len(seen_exit) == 1
              and seen_exit[0][0].startswith("precondition: the run exited (0) before its suites started") and seen_exit[0][1] is False,
              (r_exit, round(took_exit, 1), seen_exit))
        # Kills: dropping end_run() (the run would be left running), the group KILL for a run that leads its own session (its
        # child would outlive it) and the deadline test.
        check("a run that never reaches the state: reported once as a deadline, and ended (own session or not)",
              all(r is False and len(sn) == 1 and sn[0][0] == "precondition: its suites started did not happen within 1 s"
                  and rc is not None and child_gone for r, sn, rc, child_gone in results), results)
        # Positive control: the same helper, with the state reached, says nothing and leaves the run alone.
        check("a state that is reached: True, nothing reported, the run left running", ok_state is True and seen_ok == [] and left_running, (ok_state, seen_ok, left_running))

        print("a run that is signalled ends, and its directory goes with it")
        write(os.path.join(sandbox, "slowbin", "shellcheck"), "#!/usr/bin/env bash\nsleep 60 &\necho $! > \"$GRANDCHILD\"\nsleep 60\n", 0o755)
        for sig, name in ((signal.SIGTERM, "TERM"), (signal.SIGINT, "INT"), (signal.SIGHUP, "HUP")):
            base = fresh(scripts={"good.sh": "#!/usr/bin/env bash\necho fine\n"})
            grandchild = os.path.join(sandbox, f"gc-{name}")
            p = subprocess.Popen([sys.executable, os.path.join(base, "tests", "run.py"), "static"], cwd=base, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
                                 env=env(base, PATH=f"{sandbox}/slowbin:{os.environ.get('PATH', '')}", GRANDCHILD=grandchild))
            if not wait_until(p, lambda: os.path.exists(grandchild) and runs_left(base), f"{name}: the run made its directory and the suite its grandchild"):
                continue
            made = bool(runs_left(base))
            gc = int(open(grandchild).read()) if os.path.exists(grandchild) else 0
            p.send_signal(sig)
            try:
                rc = p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
                rc = None
            time.sleep(0.3)
            want = 128 + int(sig)
            check(f"{name}: the run made its directory, then exits {want} within the bound", made and rc == want, (made, rc))
            check(f"{name}: the directory is gone and the suite's grandchild is ended", not runs_left(base)
                  and (gc == 0 or not os.path.exists(f"/proc/{gc}") or open(f"/proc/{gc}/stat").read().rsplit(")", 1)[1].split()[0] == "Z"),
                  (runs_left(base), gc))
        # More suites than slots: the runner starts the next one the moment a slot frees, and a stop frees them all. The
        # runner prints a suite's output when the suite ends, so a stop that kills it instead of asking loses what the
        # running suites said (round 2 of #265).
        suites = {f"tests/test_q{i}.py": suite("print('MARK%d' % " + str(i) + ", flush=True)\n"
                                              "open(os.path.join(os.environ['STARTED'], 'q%d' % " + str(i) + "), 'w').close()\n"
                                              "import time; time.sleep(30)\n") for i in range(8)}
        for sig, name in ((signal.SIGTERM, "TERM"), (signal.SIGINT, "INT"), (signal.SIGHUP, "HUP")):
            base = fresh(files=suites)
            started = os.path.join(sandbox, f"started-{name}")
            os.makedirs(started)
            p = subprocess.Popen([sys.executable, os.path.join(base, "tests", "run.py"), "python"], cwd=base, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True, env=env(base, STARTED=started))
            if not wait_until(p, lambda: len(os.listdir(started)) >= 2, "the python section's first two suites started"):
                continue
            time.sleep(0.5)       # the suites' MARK lines are written; the runner holds them until the suites end
            before = sorted(os.listdir(started))
            p.send_signal(sig)
            try:
                out, _ = p.communicate(timeout=30)
                rc = p.returncode
            except subprocess.TimeoutExpired:
                p.kill()
                out, rc = p.communicate()[0], None
            time.sleep(0.5)
            after = sorted(os.listdir(started))
            shown = sorted(set(re.findall(r"MARK\d", out)))
            check(f"{name} during the python section: no queued suite starts, the exit is {128 + int(sig)}",
                  len(before) == 2 and after == before and rc == 128 + int(sig), (before, after, rc))
            check(f"{name} during the python section: what the two running suites had printed still reaches stdout, and no count of failures",
                  len(shown) == 2 and "FAILED_SUITES" not in out, (shown, out[-300:]))
        # The cases above signal run.py's pid alone, and their suites die on the first TERM: so they cannot tell a runner that
        # takes only TERM from one that takes INT and HUP, nor one that never KILLs a suite that ignores TERM (round 3 of
        # #265, F2). Here the whole process group is signalled, as a terminal's ^C or a closing terminal does; and a suite
        # that ignores TERM must be ended after the grace, its line kept.
        sys.path.insert(0, TESTS)
        import run_python_suites
        for sig, name in ((signal.SIGINT, "INT"), (signal.SIGHUP, "HUP")):
            base = fresh(files=suites)
            started = os.path.join(sandbox, f"started-group-{name}")
            os.makedirs(started)
            p = subprocess.Popen([sys.executable, os.path.join(base, "tests", "run.py"), "python"], cwd=base, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, start_new_session=True,
                                 env=env(base, STARTED=started))
            if not wait_until(p, lambda: len(os.listdir(started)) >= 2, "the python section's first two suites started", own_group=True):
                continue
            time.sleep(0.5)
            os.killpg(p.pid, sig)
            try:
                out, err = p.communicate(timeout=30)
                rc = p.returncode
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                (out, err), rc = p.communicate(), None
            shown = sorted(set(re.findall(r"MARK\d", out)))
            check(f"a group {name} during the python section: the exit is {128 + int(sig)} and both running suites' lines reach stdout",
                  rc == 128 + int(sig) and len(shown) == 2, (rc, shown, out[-300:], err[-600:]))
        # A group INT also reaches run.py, which asks the runner to stop by TERM: that alone ends the run and hides a runner
        # that takes no INT of its own. So INT goes to the runner and its suites only, as a terminal would send it to a
        # foreground group run.py is not in.
        base = fresh(files=suites)
        started = os.path.join(sandbox, "started-runner-INT")
        os.makedirs(started)
        p = subprocess.Popen([sys.executable, os.path.join(base, "tests", "run.py"), "python"], cwd=base, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True, env=env(base, STARTED=started))
        if wait_until(p, lambda: len(os.listdir(started)) >= 2, "the python section's first two suites started"):
            time.sleep(0.5)

            def children(pid: int) -> list[int]:
                r = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True)
                return [int(x) for x in r.stdout.split()]
            runner = next((c for c in children(p.pid) if "run_python_suites" in open(f"/proc/{c}/cmdline").read()), 0)
            for pid in [runner, *children(runner)] if runner else []:
                os.kill(pid, signal.SIGINT)
            try:
                out, _ = p.communicate(timeout=40)
            except subprocess.TimeoutExpired:
                # Not killpg: run.py shares this test's group. The runner and its suites are ended by pid.
                for pid in [runner, *children(runner)] if runner else []:
                    with contextlib.suppress(OSError):
                        os.kill(pid, signal.SIGKILL)
                p.kill()
                out = p.communicate()[0]
            shown = sorted(set(re.findall(r"MARK\d", out)))
            check("INT to the runner and its suites alone: no queued suite starts and both running suites' lines reach stdout",
                  runner != 0 and len(shown) == 2 and len(os.listdir(started)) == 2, (runner, shown, sorted(os.listdir(started)), out[-300:]))
        deaf = {"tests/test_deaf.py": suite("import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                                            "print('MARK-DEAF', flush=True)\nopen(os.environ['STARTED'], 'w').close()\ntime.sleep(60)\n")}
        base = fresh(files=deaf)
        started = os.path.join(sandbox, "started-deaf")
        p = subprocess.Popen([sys.executable, os.path.join(base, "tests", "run.py"), "python"], cwd=base, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, env=env(base, STARTED=started))
        if wait_until(p, lambda: os.path.exists(started), "the suite that ignores TERM started"):
            time.sleep(0.3)
            began = time.monotonic()
            p.send_signal(signal.SIGTERM)
            try:
                out, err = p.communicate(timeout=30)
                rc = p.returncode
            except subprocess.TimeoutExpired:
                p.kill()
                (out, err), rc = p.communicate(), None
            took = time.monotonic() - began
            # The kept line is the proof that the runner KILLed the suite itself after its grace: a runner that does not is still
            # waiting on the suite when run.py stops waiting for it, and run.py's KILL loses everything it had buffered. A
            # stopwatch adds nothing to that and fails under load (7.4 s against a 7 s bound once in twenty runs).
            check(f"a suite that ignores TERM: the runner ends it after its {run_python_suites.STOP_GRACE_S:g} s grace, exit 143, its line kept",
                  rc == 143 and "MARK-DEAF" in out, (rc, round(took, 1), out[-300:], err[-600:]))
            time.sleep(0.3)
            check("…and no process of that suite is left", not runs_left(base)
                  and subprocess.run(["pgrep", "-f", os.path.join(base, "tests", "test_deaf.py")], capture_output=True).returncode == 1)
        base = fresh(scripts={"good.sh": "#!/usr/bin/env bash\necho fine\n"})
        grandchild = os.path.join(sandbox, "gc-KILL")
        p = subprocess.Popen([sys.executable, os.path.join(base, "tests", "run.py"), "static"], cwd=base, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True,
                             env=env(base, PATH=f"{sandbox}/slowbin:{os.environ.get('PATH', '')}", GRANDCHILD=grandchild))
        if wait_until(p, lambda: os.path.exists(grandchild) and runs_left(base), "KILL: the run made its directory and the suite its grandchild", own_group=True):
            made = bool(runs_left(base))
            os.killpg(p.pid, signal.SIGKILL)       # a group KILL: no cleanup runs, the suite's processes die with it
            p.wait(timeout=20)
            gone = poll_until(lambda: not runs_left(base), 30.0)
            check("KILL to the run's group: the watcher removes the directory", made and gone, (made, runs_left(base)))

        print("a signal to the run's pid alone, while a suite keeps starting children")
        base = fresh()
        probe = os.path.join(sandbox, "probe.py")
        write(probe, (
            "import os, signal, subprocess, sys, threading, time\n"
            "sys.dont_write_bytecode = True\n"
            f"sys.path.insert(0, {TESTS!r})\n"
            "import run\n"
            "def stop(n, f):\n    raise run.Signalled(n)\n"
            "for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):\n    signal.signal(s, stop)\n"
            "mode = sys.argv[1]\n"
            "body = {'spawner': 'for i in 1 2 3 4; do sleep 37.123; done',\n"
            "        'deaf': 'trap \"\" TERM; sleep 37.456; true'}[mode]\n"
            "def hit(delay, sig):\n    threading.Timer(delay, os.kill, (os.getpid(), sig)).start()\n"
            "hit(1.0, signal.SIGTERM)\n"
            "if mode == 'deaf':\n    hit(2.0, signal.SIGINT)      # a second signal while cleanup waits out the grace\n"
            "try:\n    run.invoke(None, ['bash', '-c', body], dict(os.environ), '/')\nexcept run.Signalled:\n    print('SIGNALLED')\n"))
        for mode, needle in (("spawner", b"sleep\x0037.123"), ("deaf", b"sleep\x0037.456")):
            # Output goes to a file, not a pipe: an orphan that survives holds a pipe open and run() would wait it out.
            outfile = os.path.join(sandbox, f"probe-{mode}.out")
            with open(outfile, "w") as out:
                rc = subprocess.run([sys.executable, probe, mode], env=env(base), stdout=out, stderr=out, timeout=60).returncode
            r = subprocess.CompletedProcess([], rc, open(outfile).read(), "")
            time.sleep(0.5)
            survivors = ours(needle)
            for pid in survivors:
                with contextlib.suppress(OSError):
                    os.kill(pid, signal.SIGKILL)
            check(f"{mode}: the signal is raised through invoke and no process of the suite outlives it",
                  "SIGNALLED" in r.stdout and not survivors, (r.stdout, r.stderr, survivors))

        print("the python runner's budget per suite and its bound by memory")
        gcfile = os.path.join(sandbox, "gc-budget")
        base = fresh(files={"tests/test_hang.py": suite("import subprocess\n"
                                                        "g = subprocess.Popen(['sleep', '60'])\n"
                                                        f"open({gcfile!r}, 'w').write(str(g.pid))\n"
                                                        "print('STARTED')\nsys.stdout.flush()\nimport time\ntime.sleep(60)\n"),
                            "tests/test_ok.py": suite("print('fine')\n")})
        t0 = time.monotonic()
        r = run(base, "python", AGENT_FABRIC_TEST_SUITE_TIMEOUT_S="2")
        gc = int(open(gcfile).read()) if os.path.exists(gcfile) else 0
        time.sleep(0.3)
        check("a suite past its budget is ended within about that time and counted: FAILED_SUITES=1, exit 1, what it printed kept",
              r.returncode == 1 and time.monotonic() - t0 < 30 and "FAILED_SUITES=1" in r.stdout and "STARTED" in r.stdout
              and "still running after its 2 s budget" in r.stdout, (r.returncode, time.monotonic() - t0, r.stdout, r.stderr))
        check("…the suite's own child is ended with it", gc != 0 and (not os.path.exists(f"/proc/{gc}")
              or open(f"/proc/{gc}/stat").read().rsplit(")", 1)[1].split()[0] == "Z"), gc)
        check("…the other suite still ran and passed", "fine" in r.stdout)
        # A descendant that left the suite's tree (double fork, reparented to init) and still holds its stdout pipe.
        base = fresh(files={"tests/test_daemon.py": suite(
            "import subprocess\n"
            "subprocess.Popen(['sh', '-c', '(sleep 29.789 &) ; exit 0'], stdout=sys.stdout)\n"
            "import time\ntime.sleep(60)\n")})
        t0 = time.monotonic()
        r = run(base, "python", AGENT_FABRIC_TEST_SUITE_TIMEOUT_S="1")
        for pid in ours(b"sleep\x0029.789"):
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)
        check("a process that escaped the suite's tree and holds its pipe cannot hang the runner past its budget",
              r.returncode == 1 and time.monotonic() - t0 < 40 and "FAILED_SUITES=1" in r.stdout and "rest of its output is lost" in r.stdout and "== tests/test_daemon.py" in r.stdout,
              (r.returncode, time.monotonic() - t0, r.stdout, r.stderr))
        for bad in ("0", "-5", "soon", "nan", "inf"):
            r = run(base, "python", AGENT_FABRIC_TEST_SUITE_TIMEOUT_S=bad)
            check(f"a budget of {bad!r} is refused: exit 1 from the run, the runner's exit 2 said, no suite started",
                  "AGENT_FABRIC_TEST_SUITE_TIMEOUT_S" in r.stderr and "STARTED" not in r.stdout and r.returncode == 1, (r.returncode, r.stderr))
        sys.path.insert(0, TESTS)
        sys.dont_write_bytecode = True
        import run_python_suites as rps
        meminfo = os.path.join(sandbox, "meminfo")
        write(meminfo, f"MemTotal:  99999999 kB\nMemAvailable:  {5 * rps.SUITE_MEM_MIB * 1024 + 7} kB\n")
        check("memory_bound: MemAvailable over the assumed peak per suite, rounded down", rps.memory_bound(meminfo) == 5, rps.memory_bound(meminfo))
        write(meminfo, "MemAvailable:  1 kB\n")
        check("…never below one job", rps.memory_bound(meminfo) == 1)
        check("…memory the kernel does not state bounds nothing (None, not a guess)",
              rps.memory_bound(os.path.join(sandbox, "absent")) is None and rps.memory_bound(os.path.join(sandbox, "meminfo-less")) is None)
        write(meminfo, "MemTotal: 1 kB\n")
        check("…a file with no MemAvailable line likewise", rps.memory_bound(meminfo) is None)
        base = fresh(files={"tests/test_ok.py": suite("print('fine')\n")})
        r = run(base, "python", AGENT_FABRIC_TEST_JOBS="1000000")
        # MemAvailable moves between the test's read and the runner's, so the exact count is not asserted (it is, against a
        # fixed file, by the cases above): the line must say the request was lowered to a positive number below it.
        said = re.search(r"1000000 jobs would not fit the memory available .*: running (\d+)", r.stderr)
        check("a job count beyond what the memory allows is lowered, said on stderr, and the run goes on",
              r.returncode == 0 and (rps.memory_bound() is None or (said is not None and 1 <= int(said.group(1)) < 1000000)),
              (r.returncode, r.stderr))

        print("the helpers")
        import run as runner
        check("invoke: a command that cannot start is 127, said", runner.invoke(None, ["/nonexistent/x"], dict(os.environ), "/") == 127)
        d = os.path.join(sandbox, "leak")
        os.makedirs(d)
        before = runner.leak_snapshot(d)
        check("leak_report: nothing added is silent and false", runner.leak_report(d, before) is False)
        open(os.path.join(d, "added"), "w").close()
        with contextlib.redirect_stdout(io.StringIO()) as shown:     # the report is for a person; here it is the thing checked
            reported = runner.leak_report(d, before)
        check("leak_report: an added entry is true, and named", reported is True and "   added" in shown.getvalue(), shown.getvalue())
        # What the bash cases held before #267 retired leak-check.sh: an entry already there is never named, a name with a
        # space or a glob character is one whole line, and the count is exact.
        d2 = os.path.join(sandbox, "leak2")
        os.makedirs(os.path.join(d2, "existing"))
        before2 = runner.leak_snapshot(d2)
        for name in ("a b", "star*.py"):
            os.makedirs(os.path.join(d2, name))
        with contextlib.redirect_stdout(io.StringIO()) as shown2:
            runner.leak_report(d2, before2)
        lines = [l for l in shown2.getvalue().splitlines() if l.startswith("   ")]
        check("leak_report: exactly the added entries, whole, and never one that was there before",
              lines == ["   a b", "   star*.py"], shown2.getvalue())
        check("short_dir: the runtime directory when it is a writable directory, else /tmp",
              runner.short_dir({"XDG_RUNTIME_DIR": d}) == d and runner.short_dir({"XDG_RUNTIME_DIR": os.path.join(d, "added")}) == "/tmp"
              and runner.short_dir({}) == "/tmp")

        print("a full run takes the host's full-suite lease (j298); a partial run, CI and the opt-out do not")
        leasebin = os.path.join(sandbox, "leasebin")
        # The real lease.py behind a PATH shim, for the other holder and the probes: the real flock semantics, and no
        # dependence on the host having the fleet's pinned python (bin/fabric-lease), which CI has not.
        write(os.path.join(leasebin, "fabric-lease"),
              f"#!{sys.executable}\nimport sys\nsys.path.insert(0, {os.path.join(ROOT, 'tools', 'fabric')!r})\n"
              "import lease\nsys.exit(lease.main())\n", 0o755)
        leased_count = 0
        host_path = os.environ.get("PATH", "/usr/bin:/bin")

        def lease_world() -> tuple[str, dict[str, str]]:
            nonlocal leased_count
            leased_count += 1
            leases = os.path.join(sandbox, f"leases{leased_count}")
            os.makedirs(leases)
            return leases, {"PATH": f"{leasebin}:{host_path}", "AGENT_FABRIC_LEASES": leases, "AGENT_FABRIC_SUITE_LEASE": "1"}

        def who(leases: str) -> str:
            return subprocess.run([os.path.join(leasebin, "fabric-lease"), "full-suite", "--who"], capture_output=True, text=True,
                                  env={"PATH": host_path, "AGENT_FABRIC_LEASES": leases, "PYTHONDONTWRITEBYTECODE": "1"}).stdout

        def hold(leases: str) -> subprocess.Popen:
            h = subprocess.Popen([os.path.join(leasebin, "fabric-lease"), "full-suite", "--label", "other", "--", "sleep", "60"],
                                 env={"PATH": host_path, "AGENT_FABRIC_LEASES": leases, "PYTHONDONTWRITEBYTECODE": "1"},
                                 stdin=subprocess.DEVNULL)
            for _ in range(100):
                if who(leases).startswith("held:"):
                    break
                time.sleep(0.1)
            return h

        def marker_suite(name: str) -> str:
            return suite(f"open({os.path.join(sandbox, name)!r}, 'w').close()\n")

        # held while the run goes on, free after a FAILING one
        leases, extra = lease_world()
        base = fresh(lease=True)
        seen = os.path.join(sandbox, "seen-during")
        write(os.path.join(base, "tests/test_probe.py"), suite(
            "import subprocess\n"
            f"open({seen!r}, 'w').write(subprocess.run(['fabric-lease', 'full-suite', '--who'], capture_output=True, text=True).stdout)"
            "\nsys.exit(3)\n"))
        r = run(base, **extra)
        during = open(seen).read() if os.path.exists(seen) else ""
        check("a full run holds the lease while its suites run, recorded as tests-run (catches: a run that never takes it)",
              during.startswith("held: ") and "(tests-run)" in during, (during, r.stderr))
        check("the lease is free after a failing run (catches: a lease that outlives a failure)",
              r.returncode == 1 and who(leases).startswith("free:"), (r.returncode, who(leases)))

        # a second full run waits for the first, and says who holds it
        leases, extra = lease_world()
        holder_proc = hold(leases)
        base = fresh(lease=True, files={"tests/test_mark.py": marker_suite("ran-second")})
        second = subprocess.Popen([sys.executable, os.path.join(base, "tests", "run.py")], cwd=base, env=env(base, **extra),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL)
        time.sleep(3)
        waited = second.poll() is None and not os.path.exists(os.path.join(sandbox, "ran-second"))
        holder_proc.terminate()
        holder_proc.wait()
        try:
            _, said = second.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            second.kill()
            _, said = second.communicate()
        check("a second full run waits while the first holds the lease, saying who holds it, then runs once it is released "
              "(catches: no lease, or a lease refused instead of waited for)",
              waited and "full-suite is held by" in said and "(other)" in said and os.path.exists(os.path.join(sandbox, "ran-second")),
              (waited, said))
        check("the waiting run's lease is free again once it ends", who(leases).startswith("free:"), who(leases))

        # TERM releases
        leases, extra = lease_world()
        flag = os.path.join(sandbox, "slow-started")
        base = fresh(lease=True, files={"tests/test_slow.py": suite(f"import time\nopen({flag!r}, 'w').close()\ntime.sleep(60)\n")})
        p = subprocess.Popen([sys.executable, os.path.join(base, "tests", "run.py"), "all"], cwd=base, env=env(base, **extra),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        for _ in range(300):
            if os.path.exists(flag) and who(leases).startswith("held:"):
                break
            time.sleep(0.1)
        was_held = who(leases).startswith("held:")
        p.send_signal(signal.SIGTERM)
        try:
            code = p.wait(timeout=60)
        except subprocess.TimeoutExpired:
            p.kill()
            code = None
        check("a TERMed full run was holding the lease, exits 143, and leaves it free (catches: a lease that outlives the signal)",
              was_held and code == 143 and who(leases).startswith("free:"), (was_held, code, who(leases)))

        # a group KILL: the lease goes with the run, and only with it (review of #323, F1: under a wrapper that ran the
        # run in a group of its own, the KILL ended the wrapper, freed the lease, and the suites ran on unleased)
        leases, extra = lease_world()
        flag = os.path.join(sandbox, "killed-suite-pid")
        base = fresh(lease=True, files={"tests/test_slow.py": suite(f"import time\nopen({flag!r}, 'w').write(str(os.getpid()))\n"
                                                        "time.sleep(60)\n")})
        p = subprocess.Popen([sys.executable, os.path.join(base, "tests", "run.py"), "all"], cwd=base, env=env(base, **extra),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                             start_new_session=True)
        for _ in range(300):
            if os.path.exists(flag) and open(flag).read() and who(leases).startswith("held:"):
                break
            time.sleep(0.1)
        was_held = who(leases).startswith("held:")
        suite_pid = int(open(flag).read() or 0) if os.path.exists(flag) else 0
        os.killpg(p.pid, signal.SIGKILL)
        p.wait()
        for _ in range(100):
            if not ours(b"test_slow.py"):
                break
            time.sleep(0.1)
        left = ours(b"test_slow.py")
        free = who(leases).startswith("free:")
        for pid in left:
            os.kill(pid, signal.SIGKILL)
        check("a group KILL of a full run ends its suites and frees the lease with them, never before (catches: the lease "
              "held by a process outside the caller's group)",
              was_held and suite_pid > 0 and not left and free, (was_held, suite_pid, left, free))

        # a group KILL while the run waits for the lease leaves no directory (review of #323, N1: the watcher started
        # after the wait, so nothing removed what mkdtemp had made)
        leases, extra = lease_world()
        holder_proc = hold(leases)
        base = fresh(lease=True, files={"tests/test_mark.py": marker_suite("ran-while-held")})
        p = subprocess.Popen([sys.executable, os.path.join(base, "tests", "run.py"), "all"], cwd=base, env=env(base, **extra),
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
                             start_new_session=True)
        said = ""
        for _ in range(300):
            line = p.stderr.readline()
            said += line
            if "waiting up to" in line or not line:
                break
        made = bool(runs_left(base))
        os.killpg(p.pid, signal.SIGKILL)
        p.wait()
        p.stderr.close()
        for _ in range(100):
            if not runs_left(base):
                break
            time.sleep(0.1)
        holder_proc.terminate()
        holder_proc.wait()
        check("a group KILL of a run waiting for the lease leaves no directory behind (catches: the watcher started "
              "after the wait)",
              "waiting up to" in said and made and not runs_left(base)
              and not os.path.exists(os.path.join(sandbox, "ran-while-held")), (said, made, runs_left(base)))

        # a wait that ends with the lease still held is 75, fabric-lease's EX_TEMPFAIL
        leases, extra = lease_world()
        holder_proc = hold(leases)
        waited_s, runner.LEASE_WAIT_S = runner.LEASE_WAIT_S, 1
        try:
            with contextlib.redirect_stderr(io.StringIO()) as said:
                runner.take_lease("all", {"AGENT_FABRIC_LEASES": leases})
            outcome = "taken"
        except runner.LeaseTimeout:
            outcome = "timeout"
        finally:
            runner.LEASE_WAIT_S = waited_s
        holder_proc.terminate()
        holder_proc.wait()
        check("a wait that ends with another holder still on the lease raises LeaseTimeout, having said who holds it "
              "(catches: a run that goes on unleased after its wait)",
              outcome == "timeout" and "still held by" in said.getvalue() and "(other)" in said.getvalue(),
              (outcome, said.getvalue()))
        base = fresh(lease=True, files={"tests/test_mark.py": marker_suite("ran-after-timeout")})
        rc = subprocess.run([sys.executable, "-c", "import sys\nsys.path.insert(0, 'tests')\nimport run\n"
                             "def late(what, environ):\n    raise run.LeaseTimeout\nrun.take_lease = late\n"
                             "sys.exit(run.main(['all']))\n"], cwd=base, env=env(base, **extra), capture_output=True,
                            text=True, timeout=120)
        check("…and main() exits 75 for it, running no suite and leaving no directory",
              rc.returncode == 75 and not os.path.exists(os.path.join(sandbox, "ran-after-timeout")) and not runs_left(base),
              (rc.returncode, rc.stderr))

        # not taken, though another holds it
        leases, extra = lease_world()
        holder_proc = hold(leases)
        for label, args, more in (("a partial run (python)", ["python"], {}),
                                  ("a run in CI (GITHUB_ACTIONS set)", [], {"GITHUB_ACTIONS": "true"}),
                                  ("a run with AGENT_FABRIC_SUITE_LEASE=0", [], {"AGENT_FABRIC_SUITE_LEASE": "0"}),
                                  ("a run on a host with no lease directory", [],
                                   {"AGENT_FABRIC_LEASES": os.path.join(sandbox, "no-such-leases")})):
            base = fresh(lease=True, files={"tests/test_mark.py": marker_suite("ran-unleased")})
            if os.path.exists(os.path.join(sandbox, "ran-unleased")):
                os.remove(os.path.join(sandbox, "ran-unleased"))
            try:
                r = run(base, *args, **{**extra, **more})
                text = (r.returncode, r.stderr)
            except subprocess.TimeoutExpired:
                text = "waited for the lease"
            check(f"{label} does not wait for a held lease (catches: the lease taken without that exemption)",
                  os.path.exists(os.path.join(sandbox, "ran-unleased")) and "is held by" not in str(text), text)
        holder_proc.terminate()
        holder_proc.wait()

        # a lease the host cannot give
        leases, extra = lease_world()
        write(os.path.join(leases, "full-suite"), "", 0)     # made by hand, unreadable: the lock cannot be taken on it
        base = fresh(lease=True, files={"tests/test_mark.py": marker_suite("ran-broken")})
        r = run(base, **extra)
        check("a lease file that cannot be opened is said on stderr and the run goes on unleased (catches: a run failed by "
              "a lease the host cannot give)",
              os.path.exists(os.path.join(sandbox, "ran-broken")) and "no host lease" in r.stderr, (r.returncode, r.stderr))

    print(f"\ntest_run: {'OK' if not fails else f'{fails} FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

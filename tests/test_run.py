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
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
fails = 0


def check(label: str, good: bool, detail: object = "") -> None:
    global fails
    print(f"  {'ok  ' if good else 'FAIL'} {label}")
    if not good:
        fails += 1
        if detail != "":
            print("      " + str(detail).replace("\n", "\n      "))


def write(path: str, text: str, mode: int = 0o644) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, mode)


def tree(base: str, files: dict[str, str] | None = None, scripts: dict[str, str] | None = None) -> str:
    """A git tree holding the runner, the static checks, the python suites' runner, quiet stand-ins for the corpus lint
    and the routing check, and `files` (tests/test_*.py fakes, or anything) and `scripts` (executable)."""
    os.makedirs(os.path.join(base, "tests"))
    for name in ("run.py", "static.py", "run_python_suites.py"):
        shutil.copy(os.path.join(TESTS, name), os.path.join(base, "tests", name))
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
         "AGENT_FABRIC_TEST_JOBS": "2"}
    e.update(extra)
    return e


def run(base: str, *args: str, **extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, os.path.join(base, "tests", "run.py"), *args], cwd=base, env=env(base, **extra),
                          capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)


def runs_left(base: str) -> list[str]:
    return [n for n in os.listdir(os.path.join(os.path.dirname(base), "runtime")) if n.startswith("af-t.")]


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
        check("all passing: exit 0, FAILED_SUITES=0 and no failure line",
              r.returncode == 0 and "FAILED_SUITES=0" in r.stdout and "FAILED" not in r.stdout.replace("FAILED_SUITES", ""),
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

        print("a run that is signalled ends, and its directory goes with it")
        write(os.path.join(sandbox, "slowbin", "shellcheck"), "#!/usr/bin/env bash\nsleep 60 &\necho $! > \"$GRANDCHILD\"\nsleep 60\n", 0o755)
        for sig, name in ((signal.SIGTERM, "TERM"), (signal.SIGINT, "INT"), (signal.SIGHUP, "HUP")):
            base = fresh(scripts={"good.sh": "#!/usr/bin/env bash\necho fine\n"})
            grandchild = os.path.join(sandbox, f"gc-{name}")
            p = subprocess.Popen([sys.executable, os.path.join(base, "tests", "run.py"), "static"], cwd=base, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
                                 env=env(base, PATH=f"{sandbox}/slowbin:{os.environ.get('PATH', '')}", GRANDCHILD=grandchild))
            for _ in range(100):
                if os.path.exists(grandchild) and runs_left(base):
                    break
                time.sleep(0.1)
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
        base = fresh(scripts={"good.sh": "#!/usr/bin/env bash\necho fine\n"})
        grandchild = os.path.join(sandbox, "gc-KILL")
        p = subprocess.Popen([sys.executable, os.path.join(base, "tests", "run.py"), "static"], cwd=base, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True,
                             env=env(base, PATH=f"{sandbox}/slowbin:{os.environ.get('PATH', '')}", GRANDCHILD=grandchild))
        for _ in range(100):
            if os.path.exists(grandchild) and runs_left(base):
                break
            time.sleep(0.1)
        made = bool(runs_left(base))
        os.killpg(p.pid, signal.SIGKILL)       # a group KILL: no cleanup runs, the suite's processes die with it
        p.wait(timeout=20)
        gone = False
        for _ in range(100):
            if not runs_left(base):
                gone = True
                break
            time.sleep(0.1)
        check("KILL to the run's group: the watcher removes the directory", made and gone, (made, runs_left(base)))

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
        bound = rps.memory_bound()
        check("a job count beyond what the memory allows is lowered, said on stderr, and the run goes on",
              r.returncode == 0 and (bound is None or f"running {bound}" in r.stderr and "would not fit" in r.stderr), (r.returncode, r.stderr, bound))

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
        check("short_dir: the runtime directory when it is a writable directory, else /tmp",
              runner.short_dir({"XDG_RUNTIME_DIR": d}) == d and runner.short_dir({"XDG_RUNTIME_DIR": os.path.join(d, "added")}) == "/tmp"
              and runner.short_dir({}) == "/tmp")

    print(f"\ntest_run: {'OK' if not fails else f'{fails} FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

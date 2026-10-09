#!/usr/bin/env python3
"""bin/fabric-watch (tools/fabric/watch.py) against a fixture fabric and a
scratch ~/projects: --once prints the three blocks in order, each from its
own command; an escape in a job title reaches the terminal as `?`, never
as itself; a failing or missing command is said in its block; pull
requests are asked only of working copies whose origin is on GitHub, and
one with none open is left out; bad arguments exit 2. In-process: the pull
requests are read every --prs-every and the rest every --every, on a clock
the test drives; q and end of input leave.

Not exercised here: the cbreak mode on a real terminal and its restore."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(HERE, "bin", "fabric-watch")
TITLE = "j9 deploy \x1b]0;pwned\x07 then \x1b[2J and \u2028 done"


def put(path: str, body: str, mode: int = 0o755) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(path, mode)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail!r}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="test_fabric_watch.") as tmp:
        root, home = os.path.join(tmp, "fabric"), os.path.join(tmp, "home")
        put(f"{root}/bin/fabric-status", "#!/bin/sh\necho 'agent: pd-x'\n")
        put(f"{root}/bin/fabric-jobs", f"#!/bin/sh\n[ \"$*\" = list ] || exit 9\nprintf '%s\\n' '{TITLE}'\n")
        put(f"{root}/bin/fabric-pr",
            '#!/bin/sh\n[ "$*" = gate ] || exit 9\ncase "${PWD##*/}" in\n'
            '  quiet) echo "pr-gate: no open pull request from h/pd-x on o/quiet (branch prefix h/pd-x/)." ;;\n'
            '  *) echo "#7 pd-x (me) commits=3 in ${PWD##*/}" ;;\nesac\n')
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "GIT_"))
               and k != "CLAUDECODE"}
        env.update(HOME=home, AGENT_FABRIC_ROOT=root, AGENT_FABRIC_PYTHON=sys.executable,
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        origins = {"ssh-wc": "git@github.com:o/a.git", "https-wc": "https://github.com/o/b",
                   "ssh-wc2": "https://github.com/O/A.git/",
                   "quiet": "git@github.com:o/quiet.git", "elsewhere": "git@gitlab.com:o/c.git",
                   "lookalike": "https://github.com.evil.example/o/d"}
        for name, url in origins.items():
            subprocess.run(["git", "init", "-q", f"{home}/projects/{name}"], env=env, check=True, timeout=30)
            subprocess.run(["git", "-C", f"{home}/projects/{name}", "remote", "add", "origin", url], env=env,
                           check=True, timeout=30)
        os.makedirs(f"{home}/projects/not-a-clone")

        def run(*args: str, **extra: str) -> subprocess.CompletedProcess:
            return subprocess.run(["bash", SHIM, *args], env={**env, **extra}, stdin=subprocess.DEVNULL,
                                  capture_output=True, timeout=120)

        r = run("--once")
        out = r.stdout.decode("utf-8", "replace")
        check("--once: exit 0", r.returncode == 0, (r.returncode, r.stderr))
        heads = [out.find(h) for h in ("── status (", "── jobs ──", "── pull requests (read ")]
        check("the three blocks, in order", -1 not in heads and heads == sorted(heads), heads)
        check("status from fabric-status", "agent: pd-x" in out, out)
        check("jobs from fabric-jobs list", "j9 deploy" in out, out)
        check("no control character reaches the terminal (ESC, BEL, U+2028)",
              not any(c in out for c in "\x1b\x07\u2028"), out)
        check("…each shown as ?", "j9 deploy ?]0;pwned? then ?[2J and ? done" in out, out)
        check("pull requests from each GitHub working copy, ssh and https, by name",
              "[https-wc]\n#7 pd-x (me) commits=3 in https-wc\n[ssh-wc]\n#7 pd-x (me) commits=3 in ssh-wc" in out, out)
        check("…none asked of an origin elsewhere, or a host that only starts with github.com",
              "elsewhere" not in out and "lookalike" not in out, out)
        check("…and a working copy with none open is left out", "quiet" not in out, out)
        check("…and a second clone of one repository, however its origin is spelt, is not asked again",
              "ssh-wc2" not in out, out)

        put(f"{root}/bin/fabric-status", "#!/bin/sh\necho 'half a status'\necho 'routing: broken' >&2\nexit 3\n")
        os.remove(f"{root}/bin/fabric-jobs")
        out = run("--once").stdout.decode("utf-8", "replace")
        check("a failing command: its output, stderr after stdout, and its exit",
              "half a status\nrouting: broken\n(fabric-status: exit 3)" in out, out)
        check("a missing command: said in its block", "(fabric-jobs: not found)" in out, out)

        for bad in (["--every"], ["--every", "x"], ["--prs-every", "nan"], ["--every", "inf"], ["--bogus"]):
            r = run(*bad)
            check(f"{' '.join(bad)}: usage, exit 2", r.returncode == 2 and b"usage: fabric-watch" in r.stderr,
                  (r.returncode, r.stderr))
        r = run("--help")
        check("--help: the contract, exit 0", r.returncode == 0 and b"CONTRACT" in r.stdout, r.returncode)

    sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
    import io
    import watch

    print("in-process: the clock decides what is read")
    t = [0.0]
    asked = {"prs": 0, "status": 0}
    saved = watch.pulls, watch.run
    screens = []
    try:
        def fake_pulls(root: str, projects: str, stop=lambda: False) -> str:
            asked["prs"] += 1
            return "prs"

        def fake_run(argv: list[str], cwd: str | None = None) -> str:
            asked["status"] += argv[0].endswith("fabric-status")
            return "x"

        def fake_wait(seconds: float) -> bool:
            t[0] += seconds
            screens.append(t[0])
            return len(screens) >= 12

        watch.pulls, watch.run = fake_pulls, fake_run
        rc = watch.watch("/r", "/p", 30.0, 300.0, False, clock=lambda: t[0], wait=fake_wait, out=io.StringIO())
        check("twelve screens 30 s apart: status read on each", rc == 0 and asked["status"] == 12, asked)
        check("…pull requests at 0 s and 300 s only", asked["prs"] == 2, asked)
        watch.pulls = saved[0]
        stopped = io.StringIO()
        saved_wc = watch.working_copies
        watch.working_copies = lambda projects: ["/a", "/b"]
        try:
            # q is already typed: every wait answers it. Without the look
            # between working copies, one screen is drawn before it is read.
            rc = watch.watch("/r", "/p", 30.0, 300.0, False, clock=lambda: 0.0, wait=lambda s: True,
                             out=stopped)
        finally:
            watch.working_copies = saved_wc
        check("q while the pull requests are read: leaves before the first pr-gate, no screen",
              rc == 0 and stopped.getvalue() == "", stopped.getvalue())
    finally:
        watch.pulls, watch.run = saved

    for typed, label in ((b"xq", "q, after another key, leaves"), (b"", "input that ends leaves")):
        rfd, wfd = os.pipe()
        os.write(wfd, typed)
        os.close(wfd)
        check(label, watch.wait_for_q(5.0, rfd) is True)
        os.close(rfd)
    rfd, wfd = os.pipe()
    os.write(wfd, b"q")
    check("a wait of 0 still reads a q already typed", watch.wait_for_q(0, rfd) is True)
    os.close(rfd)
    os.close(wfd)
    rfd, wfd = os.pipe()
    os.write(wfd, b"x")
    check("another key alone: the wait runs out", watch.wait_for_q(0.2, rfd) is False)
    os.close(rfd)
    os.close(wfd)
    check("printable keeps text, replaces C1", watch.printable("a\x9bb\tc") == "a?b     c", watch.printable("a\x9bb\tc"))

    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

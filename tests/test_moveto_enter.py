#!/usr/bin/env python3
"""runtime/provisioning/moveto/moveto.py --enter (the account's side of
`moveto`, ported from the bash `enter`; ADR-040 Wave 9): what
tests/test_moveto_cli.py (the oracle for the refresh and the modes) does not
reach — the bytes of the title, the arguments it refuses, the signals the
entered shell starts with, git's reason line, and a bounded command's group.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOVETO = os.path.join(HERE, "runtime", "provisioning", "moveto", "moveto.py")
STUB = os.path.join(HERE, "runtime", "provisioning", "moveto", "enter")
sys.path.insert(0, os.path.dirname(MOVETO))
import moveto  # noqa: E402


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as home:
        env = {"PATH": "/usr/bin:/bin", "HOME": home, "LANG": "C.UTF-8"}
        if os.environ.get("AGENT_FABRIC_PYTHON"):
            env["AGENT_FABRIC_PYTHON"] = os.environ["AGENT_FABRIC_PYTHON"]

        def enter(*args: str, stdin: str = "", via_stub: bool = False) -> subprocess.CompletedProcess:
            argv = ["bash", STUB, *args] if via_stub else [sys.executable, "-I", MOVETO, "--enter", *args]
            return subprocess.run(argv, env=env, input=stdin, capture_output=True, text=True, timeout=60, cwd=home)

        print("the arguments")
        r = enter()
        check("no argument: 2, said", r.returncode == 2 and "enter needs <dir> <title>" in r.stderr, (r.returncode, r.stderr))
        r = enter(os.path.join(home, "absent"), "t")
        check("a directory that cannot be entered: 1, said", r.returncode == 1 and "moveto: cd " in r.stderr, (r.returncode, r.stderr))
        r = enter(home, "t", "--bogus")
        check("an unknown mode: said, a plain shell follows", "unknown mode '--bogus'; a plain shell" in r.stderr and r.returncode == 0, (r.returncode, r.stderr))

        print("the title and the shell")
        r = enter(home, "the tab", stdin="echo \"[$MOVETO_TITLE]\"; grep SigIgn /proc/self/status; pwd\nexit\n")
        check("OSC 1 and OSC 2 carry the title before anything else", r.stdout.startswith("\x1b]1;the tab\x07\x1b]2;the tab\x07"), repr(r.stdout[:60]))
        check("the shell has MOVETO_TITLE and the directory", "[the tab]" in r.stdout and os.path.realpath(home) in r.stdout, r.stdout)
        sig = [ln for ln in r.stdout.splitlines() if ln.startswith("SigIgn")]
        ignored = int(sig[0].split()[-1], 16) if sig else -1
        check("the shell does not inherit Python's ignored SIGPIPE", ignored >= 0 and not ignored & (1 << 12), r.stdout)
        r = enter(home, "t", stdin="exit\n", via_stub=True)
        check("through the login stub: the same entry (no mode, no clone: nothing but the shell)", r.returncode == 0 and r.stdout.startswith("\x1b]1;t\x07"), (r.returncode, r.stderr))

        print("--wait")
        r = enter(home, "t", "--wait", stdin="abc")
        check("input that ends without an Enter is a plain shell, said (a partial line is not an Enter)",
              "input ended before Enter; a plain shell, nothing activated" in r.stderr, r.stderr)
        who = subprocess.run(["id", "-un"], capture_output=True, text=True, timeout=10).stdout.strip()
        check("the one line is the login and 'Enter to activate'", f"{who} - Enter to activate\n" in r.stdout, r.stdout)

    print("git's reason line")
    check("the first error line wins", moveto.pull_reason("hint: x\nfatal: Not possible to fast-forward\nlast", 1) == "fatal: Not possible to fast-forward")
    check("ssh: and error: count, ahead of a boilerplate last line",
          moveto.pull_reason("ssh: Could not resolve hostname x\nhint: boilerplate", 1) == "ssh: Could not resolve hostname x"
          and moveto.pull_reason("error: boom\nhint: boilerplate", 1) == "error: boom")
    check("no error line: the last line", moveto.pull_reason("one\ntwo\n", 1) == "two")
    check("nothing written and the timeout status: said as a timeout", moveto.pull_reason("", 124) == "git pull timed out after 30 s")
    check("nothing written, another status: the status", moveto.pull_reason("", 3) == "git pull exit 3")

    print("a bounded command")
    with tempfile.TemporaryDirectory() as tmp:
        pidfile = os.path.join(tmp, "pid")
        t0 = time.monotonic()
        rc, _ = moveto.run_bounded(["sh", "-c", f"sleep 60 & echo $! > {pidfile}; wait"], 1)
        took = time.monotonic() - t0
        pid = int(open(pidfile).read()) if os.path.exists(pidfile) else 0
        time.sleep(0.2)
        alive = False
        try:
            os.kill(pid, 0)
            alive = open(f"/proc/{pid}/stat").read().split()[2] != "Z"
        except (OSError, ValueError):
            pass
        check("past its time: 124 within a few seconds, and its children go with it", rc == 124 and took < 15 and pid and not alive, (rc, took, pid, alive))
        check("a command that cannot start is 127", moveto.run_bounded(["no-such-command-xyz"], 5)[0] == 127)
        check("its merged output comes back when asked", moveto.run_bounded(["sh", "-c", "echo out; echo err >&2; exit 3"], 5, capture=True) == (3, "out\nerr\n"))
        check("quiet: nothing reaches this process's stdout", moveto.run_bounded(["sh", "-c", "echo hidden"], 5, quiet=True) == (0, ""))

    print(f"\ntest_moveto_enter: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

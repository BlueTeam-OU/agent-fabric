#!/usr/bin/env python3
"""tools/fabric/github/run_suite.py, through the module. The behaviour's
oracle is two managed projects' tools/checks/test_run_suite.sh, run
unchanged against the module (ADR-040 §5 rule 5); they check exit codes and
a few words. This file pins the rest: the stderr lines whole, the names
sorted and unique, the marker's variable and its removal on every path,
the suite's own arguments and exits, a suite killed by a signal, a signal
to the wrapper alone, and bash missing. Plain script: prints ok/FAIL,
exit 1 on any failure."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = [sys.executable, os.path.join(ROOT, "tools", "fabric", "github", "run_suite.py")]
MODULE = os.path.join(ROOT, "tools", "fabric", "github", "run_suite.py")
REASON = ("    bash returns 127 for these and continues, so the suite's own\n"
          "    failures counter never saw them — it may well have reported OK.\n")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as sandbox:
        tmp = os.path.join(sandbox, "tmp")
        os.makedirs(tmp)
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_", "GH_", "GIT_", "BASH_FUNC_"))}
        base.update(HOME=sandbox, TMPDIR=tmp)
        if os.environ.get("AGENT_FABRIC_PYTHON"):
            base["AGENT_FABRIC_PYTHON"] = os.environ["AGENT_FABRIC_PYTHON"]

        def suite(name: str, body: str) -> str:
            path = os.path.join(sandbox, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
            return path

        def run(*args: str, **env: str):
            r = subprocess.run([*TOOL, *args], env=dict(base, **env), capture_output=True, text=True, timeout=60)
            return r.returncode, r.stdout, r.stderr

        def leftovers() -> list[str]:
            return os.listdir(tmp)

        print("run_suite: the report")
        s = suite("broken.sh", 'zeta_cmd\nalpha_cmd\nzeta_cmd\nbash -c beta_cmd\necho "out: $1 $2"\nexit 0\n')
        rc, out, err = run(s, "one", "two words")
        check("undefined calls: exit 1 whatever the suite said", rc == 1, f"{rc} {err}")
        check("the suite's stdout untouched, its arguments passed", out == "out: one two words\n", out)
        check("each call said as it happens, then the names sorted and unique, then the reason",
              err == ("run_suite: undefined command: zeta_cmd\nrun_suite: undefined command: alpha_cmd\n"
                      "run_suite: undefined command: zeta_cmd\nrun_suite: undefined command: beta_cmd\n"
                      f"run_suite: FAIL — {s} called command(s) that do not exist:\n"
                      "    alpha_cmd\n    beta_cmd\n    zeta_cmd\n" + REASON), err)
        check("  and the marker is gone", leftovers() == [], str(leftovers()))

        s = suite("env.sh", 'echo "$AGENT_FABRIC_UNDEF_MARKER"; [[ -f "$AGENT_FABRIC_UNDEF_MARKER" ]] || exit 7\n'
                            'declare -F command_not_found_handle >/dev/null || exit 8\nexit 0\n')
        rc, out, err = run(s)
        check("the suite sees AGENT_FABRIC_UNDEF_MARKER, a file under TMPDIR, and the handler",
              rc == 0 and out.startswith(tmp + os.sep) and err == "", f"{rc} {out} {err}")
        check("  removed after a clean run", leftovers() == [], str(leftovers()))

        for code in ("0", "1", "9"):
            rc, _, err = run(suite(f"exit{code}.sh", f"exit {code}\n"))
            check(f"a suite's own exit {code} passes through", rc == int(code) and err == "", f"{rc} {err}")
        rc, _, err = run(suite("killed.sh", "kill -TERM $$\nsleep 5\n"))
        check("a suite killed by TERM is 143, as bash's $? said", rc == 143, f"{rc} {err}")
        check("  and the marker is gone", leftovers() == [], str(leftovers()))

        print("run_suite: a signal to the wrapper alone")
        started, done = os.path.join(sandbox, "started"), os.path.join(sandbox, "done")
        s = suite("slow.sh", f'touch {started}\nsleep 2\ntouch {done}\n')
        p = subprocess.Popen([*TOOL, s], env=base, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                             start_new_session=True)
        for _ in range(100):
            if os.path.exists(started):
                break
            time.sleep(0.05)
        check("control: the suite was running", os.path.exists(started))
        os.kill(p.pid, signal.SIGTERM)
        rc = p.wait(timeout=10)
        p.stderr.close()
        check("the wrapper dies of the signal", rc == -signal.SIGTERM, str(rc))
        check("  having removed its marker", leftovers() == [], str(leftovers()))
        for _ in range(100):
            if os.path.exists(done):
                break
            time.sleep(0.05)
        check("  and the suite, which got no signal, ran on to its end", os.path.exists(done))

        print("run_suite: refusals")
        rc, out, err = run()
        check("no suite: usage, exit 2", (rc, out, err) == (2, "", "run_suite: usage: run_suite.sh <suite.sh>"
                                                                  " [args...]\n"), err)
        missing = os.path.join(sandbox, "nope.sh")
        rc, out, err = run(missing)
        check("an unreadable suite: exit 2, named", (rc, out, err) == (2, "", f"run_suite: cannot read {missing}\n"),
              err)
        r = subprocess.run([sys.executable, MODULE, suite("x.sh", "exit 0\n")], env=dict(base, PATH=sandbox),
                           capture_output=True, text=True, timeout=60)
        check("no bash on PATH: exit 2, named, the marker removed",
              (r.returncode, r.stderr) == (2, "run_suite: bash is not on PATH\n") and leftovers() == [],
              f"{r.returncode} {r.stderr} {leftovers()}")

    print("ok" if not fails else f"{fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""runtime/provisioning/moveto/install.sh and the module behind it: the files
under the prefix with their modes, the manifest in its order and whole, a
re-run that changes nothing, and a failure said with exit 1. The installer
runs through its shim, as `sh`, the way the suites that install moveto run
it. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(HERE, "runtime", "provisioning", "moveto", "install.sh")
SRC = os.path.join(HERE, "runtime", "provisioning", "moveto")
FILES = (("bin/moveto", "moveto", "755"), ("share/moveto/enter", "enter", "755"), ("share/moveto/moveto.py", "moveto.py", "644"),
         ("share/moveto/rc", "rc", "644"), ("share/bash-completion/completions/moveto", "completion.bash", "644"))
MANIFEST = "share/moveto/installed.sha256"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    def mode(path: str) -> str:
        return oct(stat.S_IMODE(os.stat(path).st_mode))[2:]

    def install(prefix: str) -> subprocess.CompletedProcess:
        env = {"PATH": os.environ.get("PATH", ""), "MOVETO_PREFIX": prefix, "AGENT_FABRIC_PYTHON": sys.executable}
        return subprocess.run(["sh", SHIM], env=env, capture_output=True, text=True, timeout=120)

    with tempfile.TemporaryDirectory() as t:
        prefix = f"{t}/usr-local"
        r = install(prefix)
        check("installs, exit 0, naming the prefix and the way to try it",
              r.returncode == 0 and r.stdout == f"moveto installed to {prefix} (manifest: {prefix}/{MANIFEST}). Try: moveto --list\n", r.stdout + r.stderr)
        check("each file is a copy of its source, with its mode",
              all(open(f"{prefix}/{rel}", "rb").read() == open(f"{SRC}/{src}", "rb").read() and mode(f"{prefix}/{rel}") == m
                  for rel, src, m in FILES), str([(rel, mode(f"{prefix}/{rel}")) for rel, _, _ in FILES if os.path.exists(f"{prefix}/{rel}")]))
        check("the directories are 755", all(mode(f"{prefix}/{d}") == "755" for d in ("bin", "share/moveto", "share/bash-completion/completions")))
        want = [f"{hashlib.sha256(open(f'{SRC}/{src}', 'rb').read()).hexdigest()}  {rel}" for rel, src, _ in FILES]
        order = ["bin/moveto", "share/moveto/moveto.py", "share/moveto/enter", "share/moveto/rc", "share/bash-completion/completions/moveto"]
        got = open(f"{prefix}/{MANIFEST}").read().splitlines()
        check("the manifest has the five lines, in the shell's order, relative to the prefix",
              [ln.split("  ")[1] for ln in got] == order and sorted(got) == sorted(want), str(got))
        check("…644, and no .tmp left beside it", mode(f"{prefix}/{MANIFEST}") == "644" and not os.path.exists(f"{prefix}/{MANIFEST}.tmp"))
        r = subprocess.run(["sha256sum", "-c", "--quiet", MANIFEST], cwd=prefix, capture_output=True, text=True, timeout=60)
        check("sha256sum -c reads the manifest from the prefix", r.returncode == 0, r.stdout + r.stderr)
        before = open(f"{prefix}/{MANIFEST}").read()
        os.chmod(f"{prefix}/bin/moveto", 0o600)
        r = install(prefix)
        check("a re-run puts a changed mode back and the manifest as it was",
              r.returncode == 0 and mode(f"{prefix}/bin/moveto") == "755" and open(f"{prefix}/{MANIFEST}").read() == before)
        names = sorted(os.listdir(f"{prefix}/share/moveto"))
        check("…leaving no temporary file in the directories", not any(n.startswith(".install-") for n in names), str(names))

        blocked = f"{t}/blocked"
        open(blocked, "w").close()
        r = install(blocked)
        check("a prefix that cannot be made: exit 1, said on stderr as one line, nothing on stdout, no traceback",
              r.returncode == 1 and r.stdout == "" and r.stderr.startswith("install_moveto: ") and "Traceback" not in r.stderr
              and r.stderr.count("\n") == 1, r.stderr)

    print("test_install_moveto:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

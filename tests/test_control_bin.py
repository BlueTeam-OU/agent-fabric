#!/usr/bin/env python3
"""bin/fabric-ctl and bin/fabric-accounts: shims that exec the control plane's
Python modules on the fleet's pinned interpreter (ADR-040 Wave 8, step s8; they
ran Node before). The interpreter is stood in for by a recorder, so what is
pinned is the wiring: which module, which arguments, which environment, and the
refusal when the pin is absent."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = {"fabric-ctl": "ctl.py", "fabric-accounts": "accounts.py"}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="test_control_bin.") as tmp:
        recorder = os.path.join(tmp, "python")
        with open(recorder, "w") as f:
            f.write('#!/bin/sh\nprintf "%s\\n" "$AGENT_FABRIC_ROOT"\nfor a in "$@"; do printf "%s\\n" "$a"; done\nexit 7\n')
        os.chmod(recorder, 0o755)
        base = {"PATH": "/usr/bin:/bin", "HOME": tmp}
        for name, module in MODULES.items():
            shim = os.path.join(HERE, "bin", name)
            print(name)
            r = subprocess.run([shim, "states", "--follow", "a b"], capture_output=True, text=True, timeout=30,
                               env={**base, "AGENT_FABRIC_PYTHON": recorder})
            lines = r.stdout.split("\n")
            check("execs the pinned interpreter on the Python module, arguments intact, status passed through",
                  r.returncode == 7 and lines[1:5] == [os.path.join(HERE, "tools", "fabric", "control", module),
                                                       "states", "--follow", "a b"], (r.returncode, r.stdout, r.stderr))
            check("AGENT_FABRIC_ROOT is this checkout", lines[0] == HERE, lines[:1])
            r = subprocess.run([shim], capture_output=True, text=True, timeout=30,
                               env={**base, "AGENT_FABRIC_PYTHON": os.path.join(tmp, "absent")})
            check("no interpreter at the pin: exit 127, one line naming it, nothing on stdout",
                  r.returncode == 127 and r.stdout == "" and "absent" in r.stderr and len(r.stderr.strip().split("\n")) == 1,
                  (r.returncode, r.stdout, r.stderr))
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

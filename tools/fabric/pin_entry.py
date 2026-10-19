"""tools/fabric/pin_entry.py — what a module run as a script does first, before
any import that needs the fleet's pinned Python (agent-fabric ADR-040 §5 rule 7).

Run under another interpreter, `ensure` execs the pin on the same script with -I
and the same argv; with no pin installed it prints the install command and
exits 127, the line the provisioning shims printed. Standard library only and
syntax every supported `python3` reads, because it runs before the pin does.
"""
from __future__ import annotations

import os
import sys

PINNED = "/usr/local/bin/fabric-python"
# Exec once, then trust the marker: a wrapper set as AGENT_FABRIC_PYTHON (a
# pyenv shim, a script that execs python) is never sys.executable, and
# comparing identities would re-exec forever (the same trap as gzcoord/entry.py).
EXECED = "AGENT_FABRIC_PIN_EXECED"


def ensure(script: str, label: str) -> None:
    py = os.environ.get("AGENT_FABRIC_PYTHON") or PINNED
    execed = os.environ.pop(EXECED, None) == "1"
    if execed or os.path.realpath(sys.executable) == os.path.realpath(py):
        return
    if not os.access(py, os.X_OK):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(script))))
        sys.stderr.write(
            "%s: the fleet's pinned Python is not installed at %s; as root: "
            "/usr/bin/python3 %s/tools/fabric/python_pin.py install\n" % (label, py, root))
        sys.exit(127)
    os.environ[EXECED] = "1"
    os.execv(py, [py, "-I", script] + sys.argv[1:])

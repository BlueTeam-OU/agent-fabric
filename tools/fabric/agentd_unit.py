"""tools/fabric/agentd_unit.py — the control agent's unit, as bootstrap
installs it and fabric-status reads it back (ADR-040 Wave 8, step s8: the
Node control agent is deleted, tools/fabric/control/agentd.py is the one).

runtime/control/agent-fabric-agentd.service is the unit, installed as it is:
its ExecStart runs the pinned interpreter on tools/fabric/control/agentd.py.
Until s8 a selector (runtime/control/agentd.json) chose, per login, between
that and the Node agent, and bootstrap fell back to Node where Python could
not run. There is no second implementation to fall back to: where the pinned
interpreter is not here the unit is installed all the same, and said not to
be able to start, because the account's control agent is something the
coordinator reaches it by and a quiet gap would look like a silent account.
Standard library only.
"""
from __future__ import annotations

import os

# python_pin.py's link, fixed: its AGENT_FABRIC_PYTHON_LINK override is for a
# test's reader, and a unit holding a test's path would outlive the test. The
# shims' default is the same path; a bare python3 would be whatever the
# user manager's PATH finds first, not the pin.
FABRIC_PYTHON = "/usr/local/bin/fabric-python"


def python_refusal() -> str:
    """Why the unit cannot start here; "" when the pinned interpreter is."""
    if not os.access(FABRIC_PYTHON, os.X_OK):
        return f"{FABRIC_PYTHON} is not executable (as root: tools/fabric/python_pin.py install)"
    return ""


def implementation_of(unit: str) -> str | None:
    """What an installed unit runs, from its ExecStart: "python" for the
    control agent, "node" for the deleted Node one an account not yet
    bootstrapped may still carry, None for anything else."""
    for line in unit.splitlines():
        if line.startswith("ExecStart="):
            argv = line[len("ExecStart="):].split()
            if any(a.endswith("/control/agentd.py") for a in argv):
                return "python"
            if any(a.endswith("/control/agentd.mjs") for a in argv):
                return "node"
    return None

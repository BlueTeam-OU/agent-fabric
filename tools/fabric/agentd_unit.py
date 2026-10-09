"""tools/fabric/agentd_unit.py — which implementation of the control agent
an account's unit runs (ADR-040 Wave 8, step s7: the cutover from
runtime/control/agentd.mjs to tools/fabric/control/agentd.py).

runtime/control/agentd.json is the selector: a default, node or python, and
the logins that run python ahead of it. bootstrap.py writes the unit from
it, lint holds its shape and its logins to the host registry, and
fabric-status reads the installed unit back. The wire is the same either
way (the parity suite's byte-equal replies), so nothing a reply carries
says which one answered: the unit's ExecStart is where that is read.
Standard library only.
"""
from __future__ import annotations

import json
import os

SELECTOR_REL = os.path.join("runtime", "control", "agentd.json")
IMPLEMENTATIONS = ("node", "python")
KEYS = frozenset({"description", "default", "python"})
# python_pin.py's link, fixed: its AGENT_FABRIC_PYTHON_LINK override is for a
# test's reader, and a unit holding a test's path would outlive the test. The
# shims' default is the same path; a bare python3 would be whatever the
# user manager's PATH finds first, not the pin.
FABRIC_PYTHON = "/usr/local/bin/fabric-python"
# %h as in the unit's other lines: every account's checkout is
# ~/projects/agent-fabric. No arguments: the daemon, as `node agentd.mjs` is.
PYTHON_EXEC_START = f"ExecStart={FABRIC_PYTHON} %h/projects/agent-fabric/tools/fabric/control/agentd.py"


def problems(doc: object) -> list[str]:
    """What is wrong with a selector's shape, one line each; [] when sound."""
    if not isinstance(doc, dict):
        return ["not a JSON object"]
    out = [f"unknown key {k!r}" for k in sorted(set(doc) - KEYS)]
    if "description" in doc and not isinstance(doc["description"], str):
        out.append("description is not a string")
    if doc.get("default") not in IMPLEMENTATIONS:
        out.append(f"default is {doc.get('default')!r}; it is node or python")
    logins = doc.get("python", [])
    if not isinstance(logins, list) or not all(isinstance(x, str) and x for x in logins):
        out.append("python is not a list of logins")
    elif len(set(logins)) != len(logins):
        out.append("python names a login twice")
    return out


def load(root: str) -> dict:
    """The selector under `root`; ValueError, in one line, when it cannot be
    read or is not sound — the caller then leaves the unit as it is."""
    path = os.path.join(root, SELECTOR_REL)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except OSError as e:
        raise ValueError(f"{SELECTOR_REL} unreadable: {e.strerror or e}") from None
    except ValueError as e:
        raise ValueError(f"{SELECTOR_REL} is not JSON: {e}") from None
    found = problems(doc)
    if found:
        raise ValueError(f"{SELECTOR_REL} invalid: {'; '.join(found)}")
    return doc


def implementation(doc: dict, login: str) -> str:
    return "python" if login in doc.get("python", []) else doc["default"]


def unit_text(template: str, impl: str) -> str:
    """The unit for `impl` from the fabric's unit file. Node is the file as it
    is, byte for byte, so an account that stays on node sees no change and
    its daemon no restart. Python swaps the one ExecStart line and nothing
    else: the environment, working directory and restart policy are the
    Node daemon's, which the Python one reads the same way."""
    if impl == "node":
        return template
    lines = template.split("\n")
    at = [i for i, line in enumerate(lines) if line.startswith("ExecStart=")]
    if len(at) != 1:
        raise ValueError(f"the unit file has {len(at)} ExecStart lines, not one")
    lines[at[0]] = PYTHON_EXEC_START
    return "\n".join(lines)


def implementation_of(unit: str) -> str | None:
    """Which implementation an installed unit runs, from its ExecStart; None
    when it names neither."""
    for line in unit.splitlines():
        if line.startswith("ExecStart="):
            argv = line[len("ExecStart="):].split()
            if any(a.endswith("/control/agentd.py") for a in argv):
                return "python"
            if any(a.endswith("/control/agentd.mjs") for a in argv):
                return "node"
    return None

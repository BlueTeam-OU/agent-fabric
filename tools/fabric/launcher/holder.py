"""tools/fabric/launcher/holder.py — the holder's addenda of the bound role, read for the prompt (agent-fabric ADR-060).
A part of tools/fabric/launch.py, whose docstring is the contract.

The reading is addenda.py's, run as a helper like the identity and the
prompt render: by path, under -I, its refusal one line on stderr. Here only
the catalogue's policy for the role and the file the render takes."""
from __future__ import annotations

import json
import os
import sys

from fabric_launcher.base import HERE, die, helper, stripped

HOLDER_FILE = "launch-holder.json"


def policy(fabric_root: str, role: str) -> str:
    """holders_specialize of the role in the catalogue: "optional" unless it
    says "required" (rule 7). A catalogue that is missing is the fixture of a
    test, which has no roles to specialise; one that cannot be read or holds a
    value that is neither stops the launch: the flag exists so that a role
    whose shared text names no jurisdiction is never launched without one."""
    path = os.path.join(fabric_root, "identities", "roles", "catalog.json")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return "optional"
    except (OSError, ValueError) as e:
        die(f"{path} could not be read ({type(e).__name__}), so whether {role} needs holder addenda is unknown.")
    entries = [r for r in doc.get("roles", []) if isinstance(r, dict) and r.get("id") == role] if isinstance(doc, dict) else []
    value = entries[0].get("holders_specialize", "optional") if entries else "optional"
    if value not in ("optional", "required"):
        die(f"{path}: holders_specialize of {role} is {value!r}, not optional or required.")
    return value


def read(fabric_root: str, agent: str, role: str, state_dir: str) -> tuple[str, str] | None:
    """(store sha, addenda commit) and the Holder at state_dir/launch-holder.json,
    or None with no such file left over from an earlier launch: no addenda."""
    out = os.path.join(state_dir, HOLDER_FILE)
    try:
        os.unlink(out)
    except FileNotFoundError:
        pass
    r = helper([sys.executable, "-I", os.path.join(HERE, "addenda.py"), "--login", agent, "--role", role,
                "--policy", policy(fabric_root, role), "--out", out])
    if r is None or r.returncode != 0:
        die(f"the holder addenda of role {role} could not be read (tools/fabric/addenda.py); the launch stops.")
    answer = stripped(r).split()
    if not answer:
        return None
    if len(answer) != 2:
        die("tools/fabric/addenda.py answered something else than a store sha and a commit.")
    return answer[0], answer[1]

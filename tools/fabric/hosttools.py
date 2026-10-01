#!/usr/bin/env python3
"""tools/fabric/hosttools.py — is the host tooling installed from this
repository the same as the repository's copy?

moveto lives under /usr/local (runtime/provisioning/moveto/install.sh);
the source is here. Nothing re-installs it when the source changes, so
the check is made where a session already looks: bin/fabric-status
calls moveto_drift() on every run.

    hosttools.py            # one line per tool, exit 1 on drift
"""
from __future__ import annotations

import hashlib
import os
import sys

FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
MOVETO_FILES = {"moveto": "bin/moveto", "moveto.py": "share/moveto/moveto.py", "enter": "share/moveto/enter",
                "rc": "share/moveto/rc",
                "completion.bash": "share/bash-completion/completions/moveto"}
MANIFEST = "share/moveto/installed.sha256"


def _sha(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def moveto_drift(prefix: str | None = None, root: str | None = None) -> dict:
    """{installed, status, detail}: status is 'absent' (nothing under the
    prefix), 'in sync', or 'drift' with the files that differ — from the
    repository (re-run install.sh) or from the manifest (edited in place)."""
    prefix = prefix or os.environ.get("MOVETO_PREFIX") or "/usr/local"
    root = root or FABRIC_ROOT
    src = os.path.join(root, "runtime", "provisioning", "moveto")
    installed = {n: _sha(os.path.join(prefix, rel)) for n, rel in MOVETO_FILES.items()}
    if not any(installed.values()):
        return {"installed": False, "status": "absent", "detail": f"no moveto under {prefix}"}
    recorded: dict[str, str] = {}
    try:
        with open(os.path.join(prefix, MANIFEST), encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) == 2:
                    recorded[parts[1]] = parts[0]
    except OSError:
        pass
    stale, edited, missing = [], [], []
    for name, rel in MOVETO_FILES.items():
        here, there = _sha(os.path.join(src, name)), installed[name]
        if there is None:
            missing.append(rel)
        elif here != there:
            stale.append(rel)
        if there is not None and recorded and recorded.get(rel) not in (None, there):
            edited.append(rel)
    if not (stale or edited or missing):
        return {"installed": True, "status": "in sync",
                "detail": f"{prefix} matches runtime/provisioning/moveto" + ("" if recorded else " (no manifest: installed before install.sh recorded one)")}
    bits = []
    if stale:
        bits.append("behind the repository: " + ", ".join(stale) + f" — sudo {os.path.join(src, 'install.sh')}")
    if edited:
        bits.append("edited in place since install: " + ", ".join(edited))
    if missing:
        bits.append("missing: " + ", ".join(missing))
    return {"installed": True, "status": "drift", "detail": "; ".join(bits)}


if __name__ == "__main__":
    r = moveto_drift()
    print(f"moveto       {r['status']}: {r['detail']}")
    sys.exit(1 if r["status"] == "drift" else 0)

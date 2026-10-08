"""The argv the managed projects' tree checks share: [--root <dir>]
[-h|--help], and the root they default to. One reading, so the checks
refuse alike (devex-tooling's port contracts 5/8 and 6/8)."""
from __future__ import annotations

import subprocess


class Refused(Exception):
    """Could not check: the message is the stderr line after "<me>: "."""


def parse_root(argv: list[str]) -> str | None:
    """The --root given, "" for none; None when --help was asked."""
    root, i = "", 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            return None
        if a == "--root":
            if i + 1 >= len(argv):
                raise Refused("--root needs a value")
            root, i = argv[i + 1], i + 2
            continue
        raise Refused(f"unexpected argument: {a}")
    return root


def toplevel() -> str:
    """The working directory's git toplevel: the root when none is given."""
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        r = None
    if r is None or r.returncode != 0 or not r.stdout.strip():
        raise Refused("not in a git working copy; pass --root <dir>")
    return r.stdout.strip()

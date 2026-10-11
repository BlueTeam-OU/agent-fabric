#!/usr/bin/env python3
"""tools/fabric/fabric_locale.py — what a locale's translator needs from the
fabric: the dispatch of bin/fabric-locale (agent-fabric ADR-040 Wave 9, batch 1).
The bin/ path is a forwarder that checks the pinned Python and execs this.

A translation is authored by the locale's holder and checked by lint; this
prints the two things lint will hold it to, so the holder checks itself before
opening the PR (docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md).

THE CONTRACT (frozen from the bash, ADR-040 §5 rule 3)
  fabric-locale tokens <source.md>   the protected tokens of an English source:
                                     tools/fabric/lint.py --tokens <source.md>
  fabric-locale digest <source.md>   the source's body digest:
                                     tools/fabric/lint.py --digest <source.md>
  Exactly one path follows the verb; otherwise stderr
  "usage: fabric-locale tokens <source.md>" (or "digest …") and exit 2. No verb, or any other
  word: stderr "usage: fabric-locale tokens|digest <source.md>", exit 2. The
  pin check comes first (the forwarder's), so a host without the pin says so
  before any usage error. lint's stdout, stderr and exit status are untouched:
  this process is replaced by it (os.execv), on the interpreter the forwarder
  named (AGENT_FABRIC_PYTHON, the one variable read; else sys.executable).
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LINT = os.path.join(HERE, "lint.py")


def main(argv: list[str]) -> int:
    verb = argv[1] if len(argv) > 1 else ""
    if verb in ("tokens", "digest"):
        if len(argv) != 3:
            sys.stderr.write(f"usage: fabric-locale {verb} <source.md>\n")
            return 2
        py = os.environ.get("AGENT_FABRIC_PYTHON") or sys.executable
        os.execv(py, [py, LINT, f"--{verb}", argv[2]])
    sys.stderr.write("usage: fabric-locale tokens|digest <source.md>\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

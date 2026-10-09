#!/usr/bin/env python3
"""A test that builds the fabric tree it runs a tool on owns that tree's
instance data (agent-fabric ADR-045 rule 3): it starts without the runner's
AGENT_FABRIC_OPERATOR, which would outrank the tree the tool is handed. The
suites below build such trees (a role, a lint root, a launcher fabric, a fleet
registry) and failed, 7 of them, when the runner exported an operator. Running
them all with one exported costs minutes (lint and assemble alone take over a
minute each), so this holds the cheap half: the helper does what it says and
each of those suites calls it before anything else runs. The whole-suite run
with an operator exported is the check that found them. Plain script."""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree  # noqa: E402

SUITES = ("assemble", "assemble_seams", "fleet", "identity", "launch_prompt", "lint", "role")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    saved = os.environ.get("AGENT_FABRIC_OPERATOR")
    try:
        os.environ["AGENT_FABRIC_OPERATOR"] = "/nonexistent/operator"
        own_instance_tree()
        check("the helper drops an exported operator", "AGENT_FABRIC_OPERATOR" not in os.environ)
        own_instance_tree()
        check("…and is fine with none", "AGENT_FABRIC_OPERATOR" not in os.environ)
    finally:
        if saved is None:
            os.environ.pop("AGENT_FABRIC_OPERATOR", None)
        else:
            os.environ["AGENT_FABRIC_OPERATOR"] = saved
    for name in SUITES:
        with open(os.path.join(HERE, f"test_{name}.py"), encoding="utf-8") as fh:
            src = fh.read()
        check(f"test_{name} starts without the runner's operator",
              re.search(r"^own_instance_tree\(\)$", src, re.M) is not None
              and "from instance_fixtures import own_instance_tree" in src)
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

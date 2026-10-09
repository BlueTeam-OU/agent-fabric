#!/usr/bin/env python3
"""A test that builds the fabric tree it runs a tool on owns that tree's
instance data (agent-fabric ADR-045 rule 3): it starts without the runner's
AGENT_FABRIC_OPERATOR, which would outrank the tree the tool is handed
(tools/fabric/roots.py) and make the tool read the operator's data instead of
the fixture's. A suite that names AGENT_FABRIC_ROOT builds or points at such a
tree, so each one either calls own_instance_tree() as a module-level statement
before any definition runs, or names AGENT_FABRIC_OPERATOR itself (it sets or
clears it for the cases that mean one). The rule is discovered, not listed: a
suite added tomorrow that names AGENT_FABRIC_ROOT is held to it. Running every
suite with an operator exported costs most of the suite's run (lint and
assemble alone take minutes), so this holds the cheap half, and the
whole-suite run with an operator exported is the check that found the class
(see the PR that added this). Plain script."""
from __future__ import annotations

import ast
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree  # noqa: E402


def starts_without_operator(src: str) -> bool:
    """own_instance_tree() is a statement of the module itself (not of a function or an
    `if __name__` block) and comes before the first function, class or guard."""
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.If)):
            return False
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name) and node.value.func.id == "own_instance_tree"):
            return True
    return False


# Suites of the guards' authority (policies/authority.json: not python-dev's entry,
# fabric-coordinator's): they set AGENT_FABRIC_ROOT to a tree they build, and are
# left to the owner of those guards to start without the operator.
NOT_PYTHON_DEVS = ("test_agent_fabric_dir_authority.py", "test_charter_authority.py", "test_contributors.py")


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

    ok_src = "import os\nfrom instance_fixtures import own_instance_tree\nown_instance_tree()\n\ndef main():\n    pass\n"
    check("positive control: the call before any definition is accepted", starts_without_operator(ok_src))
    for label, src in (("after a definition", "def main():\n    pass\n\nown_instance_tree()\n"),
                       ("inside the entry guard", "def main():\n    pass\n\nif __name__ == '__main__':\n    own_instance_tree()\n"),
                       ("inside a function", "def setup():\n    own_instance_tree()\n"),
                       ("absent", "import os\n\ndef main():\n    pass\n")):
        check(f"negative control: the call {label} is refused", not starts_without_operator(src))

    held = 0
    for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        if "AGENT_FABRIC_ROOT" not in src or "AGENT_FABRIC_OPERATOR" in src or os.path.basename(path) in NOT_PYTHON_DEVS:
            continue
        held += 1
        check(f"{os.path.basename(path)} starts without the runner's operator", starts_without_operator(src),
              "it names AGENT_FABRIC_ROOT, so it calls own_instance_tree() before any definition (tests/instance_fixtures.py)")
    check("the scan found suites to hold", held >= 25, held)
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

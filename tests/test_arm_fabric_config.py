#!/usr/bin/env python3
"""agent-fabric's own arm.json (projects/agent-fabric/integration/gh/arm.json):
arm.sh refused the fabric itself while it had none ("the security boundary
cannot be judged", python-dev-01 on #110). It loads, its cases are boundary,
prose and translations are not, and no role but the owner waives it."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric", "github"))
import arm  # noqa: E402

CONFIG = os.path.join(HERE, "projects", "agent-fabric", "integration", "gh", "arm.json")


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    paths, exempt, classes, waiver = arm.load_config(CONFIG)

    def boundary(f: str) -> bool:
        return not (exempt and exempt.search(f)) and bool(paths.search(f))
    check("it loads, its cases are boundary (load_config refuses a case the patterns miss)", True)
    for f in ("tools/fabric/guards/agent_fabric_dir_authority.py", "tools/fabric/secretstore/core.py",
              "runtime/control/agentd.mjs", "policies/githooks/pre-commit"):
        check(f"{f}: boundary", boundary(f))
    for f in ("docs/adr/ADR-018-authority.md", "identities/roles/language-culture/locale/ge/charter.md",
              "tools/fabric/lint_rules/locales.py", "README.md"):
        check(f"{f}: not boundary", not boundary(f))
    check("no classes", classes == {})
    check("no role waives the boundary: the owner arms it", waiver is None)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

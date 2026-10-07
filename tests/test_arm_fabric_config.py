#!/usr/bin/env python3
"""The projects' arm.json files (projects/<id>/integration/gh/arm.json):
arm.sh refused a project with none ("the security boundary cannot be
judged": agent-fabric itself on #110, the gateway on its #5). Each loads,
its cases are boundary, and the paths each says are not boundary are not;
no role but the owner waives agent-fabric's or the gateway's."""
from __future__ import annotations

import glob
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
    for cfg in sorted(glob.glob(os.path.join(HERE, "projects", "*", "integration", "gh", "arm.json"))):
        rel = os.path.relpath(cfg, HERE)
        try:
            arm.load_config(cfg)
            check(f"{rel} loads, its cases boundary", True)
        except Exception as e:  # noqa: BLE001 - the case says which and why
            check(f"{rel} loads, its cases boundary ({type(e).__name__}: {e})", False)
    gw = os.path.join(HERE, "projects", "agent-fabric-gateway", "integration", "gh", "arm.json")
    gp, ge, _, gw_waiver = arm.load_config(gw)

    def gw_boundary(f: str) -> bool:
        return not (ge and ge.search(f)) and bool(gp.search(f))
    for f in ("crates/test-support/src/lib.rs", "tests/anthropic-passthrough/tests/stream.rs",
              "fixtures/anthropic/count_tokens/request.json", "xtask/src/main.rs",
              "architecture/roadmap/BOTTOM-UP-IMPLEMENTATION-PLAN.md", "architecture/adr/ADR-003-x.md",
              ".agent-fabric/taxonomy.json", "README.md"):
        check(f"gateway {f}: not boundary", not gw_boundary(f))
    check("gateway: no role waives the boundary", gw_waiver is None)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

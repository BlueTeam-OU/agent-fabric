#!/usr/bin/env python3
"""The projects' arm.json files (projects/<id>/integration/gh/arm.json):
arm.sh refused a project with none ("the security boundary cannot be
judged": agent-fabric itself on #110, the gateway on its #5). Each loads,
its cases are boundary, and the paths each says are not boundary are not;
no role but the owner waives agent-fabric's, the gateway's or
radicle-spike's (whose PRs could not be armed without one, 2026-10-08)."""
from __future__ import annotations

import ast
import glob
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric", "github"))
import arm  # noqa: E402

CONFIG = os.path.join(HERE, "projects", "agent-fabric", "integration", "gh", "arm.json")


def arm_closure() -> set[str]:
    """Every module arm.py imports, directly or through another, found on
    the two roots it puts on sys.path (tools/fabric, tools/fabric/github):
    the files whose change changes what an arm decides. Computed, not
    listed, so a new import is caught the day it is added."""
    fabric = os.path.join(HERE, "tools", "fabric")
    roots_ = (fabric, os.path.join(fabric, "github"))

    def find(dotted: str) -> str | None:
        parts = dotted.split(".")
        for root in roots_:
            base = os.path.join(root, *parts)
            for cand in (base + ".py", os.path.join(base, "__init__.py")):
                if os.path.isfile(cand):
                    return cand
        return None

    seen: set[str] = set()
    todo = [os.path.join(fabric, "github", "arm.py")]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        tree = ast.parse(open(f, encoding="utf-8").read(), f)
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            for n in names:
                for i in range(1, n.count(".") + 2):
                    hit = find(".".join(n.split(".")[:i]))
                    if hit and hit not in seen:
                        todo.append(hit)
    return {os.path.relpath(f, HERE) for f in seen}


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
              "tools/fabric/control/agentd.py", "runtime/control/agent-fabric-agentd.service",
              "policies/githooks/pre-commit"):
        check(f"{f}: boundary", boundary(f))
    for f in ("docs/adr/ADR-018-authority.md", "identities/roles/language-culture/locale/ge/charter.md",
              "tools/fabric/lint_rules/locales.py", "README.md"):
        check(f"{f}: not boundary", not boundary(f))
    check("no classes", classes == {})
    check("no role waives the boundary: the owner arms it", waiver is None)
    closure = arm_closure()
    gh_dir = os.path.join("tools", "fabric", "github") + os.sep
    inside = sorted(f for f in closure if f.startswith(gh_dir))
    check(f"arm.py's import closure reaches into github/ ({len(inside)} modules)", len(inside) >= 10)
    for f in inside:
        check(f"{f}: in arm.py's import closure, boundary", boundary(f))
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
    # Each exempt tree sampled with a file its patterns WOULD select (a word
    # in the name), so dropping that exemption turns a check red.
    for f in ("crates/test-support/src/token.rs", "tests/security/tests/auth.rs",
              "fixtures/anthropic/count_tokens/request.json", "xtask/src/signing.rs",
              "architecture/roadmap/BOTTOM-UP-IMPLEMENTATION-PLAN.md", "architecture/adr/ADR-003-x.md",
              ".agent-fabric/taxonomy.json", "README.md"):
        check(f"gateway {f}: not boundary", not gw_boundary(f))
    check("gateway: no role waives the boundary", gw_waiver is None)
    rs = os.path.join(HERE, "projects", "radicle-spike", "integration", "gh", "arm.json")
    rp, re_, _, rs_waiver = arm.load_config(rs)

    def rs_boundary(f: str) -> bool:
        return not (re_ and re_.search(f)) and bool(rp.search(f))
    # The findings are prose about the seed and its keys: a word the patterns
    # select, exempt as Markdown.
    for f in ("findings/01-seed-on-host.md", "findings/02-key-and-trust.md", ".agent-fabric/taxonomy.json", "README.md"):
        check(f"radicle-spike {f}: not boundary", not rs_boundary(f))
    check("radicle-spike: no role waives the boundary", rs_waiver is None)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

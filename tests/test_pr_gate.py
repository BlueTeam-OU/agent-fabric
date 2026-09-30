#!/usr/bin/env python3
"""Tests for tools/fabric/github/pr_gate.py's internals; the behaviour is
runtime/github/test_pr-gate.sh's, run unchanged against the shim (ADR-040
§5 rule 5). What the oracle does not pin: the band's edges, which it
tests only at 6, 9 and 17."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from github import pr_gate  # noqa: E402

CLEAR = {"mergeable": "MERGEABLE", "checks": "green", "unresolved": "0", "queue": "", "armed": "no"}


def commits(work: int) -> dict:
    return {"work": work, "fix": 0, "merge": 0, "netted": 0, "fix_subjects": [], "netted_subjects": []}


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    print("the band's edges")
    v = lambda w: pr_gate.verdict(1, "main", False, commits(w), CLEAR, "head reviewed", [])  # noqa: E731
    check("7 work: ask the owner", v(7).startswith("MERGEABLE — ask the owner (7 work commits < 8)"))
    check("8 work: arm", v(8).startswith("MERGEABLE — arm: post the basis (8 work commits"))
    check("16 work: arm", v(16).startswith("MERGEABLE — arm: post the basis (16 work commits"))
    check("17 work: over 16, still mergeable", v(17).startswith("MERGEABLE — 17 work commits, over 16"))
    check("unknown commits: by hand", pr_gate.verdict(1, "main", False, None, CLEAR, "head reviewed", [])
          .startswith("MERGEABLE — commits unknown"))
    check("a queue position wins over every block",
          pr_gate.verdict(1, "main", True, commits(9), dict(CLEAR, queue="2"), "none", []).startswith("QUEUED"))

    print("AWAITING-SUPPLY")
    body = "AWAITING-SUPPLY: h/db-admin\n - AWAITING-SUPPLY: web-dev-01\naaaaaaa1..bbbbbbb2: web-dev-01 (web-dev)"
    check("the unmet login, by its last segment", pr_gate.awaiting_supply(body) == ["db-admin"])
    check("a range line for a longer login does not meet a shorter one",
          pr_gate.awaiting_supply("AWAITING-SUPPLY: web\naaaaaaa1..bbbbbbb2: web-dev") == ["web"])
    check("a login with a regex character is matched literally, never a crash",
          pr_gate.awaiting_supply("AWAITING-SUPPLY: a+b\naaaaaaa1..bbbbbbb2: aab") == ["a+b"])
    check("no body, nothing awaited", pr_gate.awaiting_supply("") == [])

    print("owner and jq's semantics")
    check("<host>/<login>/… names its session", pr_gate.owner_of("h/l/feat/x") == "h/l")
    check("two segments are their first", pr_gate.owner_of("h/l") == "h")
    check("jq's // skips null and false", pr_gate.alt(None, False, "", "x") == "")
    check("a null reads null in interpolation", pr_gate.jq_str(None) == "null")
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

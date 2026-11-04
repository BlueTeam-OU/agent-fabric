#!/usr/bin/env python3
"""The registry-id grammar (tools/fabric/registry_id.py) admits every project the registry holds.

A REQUEST for a project with a dot in its id (gzapi.ge, blueteam.brand) was
refused by three copies of a slug pattern that had no dot (2026-10-25). The
grammar is now one pattern the three consumers import; this holds the
registry and the grammar together, so a project added to
projects/registry.json that the grammar refuses fails here, not on the
first REQUEST sent for it.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import jobs as jobs_tool  # noqa: E402
import registry_id  # noqa: E402
from control import jobs as control_jobs  # noqa: E402
from gzcoord import intake  # noqa: E402

GOOD = ["a", "0", "agent-fabric", "gzapi.ge", "blueteam.brand", "a.b.c", "a1-b2.c3", "a" * 63, "a-.b"]   # a-.b: an inner segment may end in a hyphen, as decided
BAD = ["", "a" * 64, ".a", "a.", "a..b", "-a", "a-", "a.-b", "A", "a_b", "a b", "a/b", "../etc", "a\n", "é", "a.b-"]


def test_every_registry_id_matches_the_grammar() -> None:
    with open(os.path.join(ROOT, "projects", "registry.json"), encoding="utf-8") as fh:
        ids = list(json.load(fh)["projects"])
    assert ids, "the registry names no project: the check would pass on nothing"
    refused = [i for i in ids if not registry_id.REGISTRY_ID.fullmatch(i)]
    assert not refused, f"registry ids the grammar refuses: {refused}"
    assert any("." in i for i in ids), "no registry id has a dot any more: GOOD's dotted cases carry that check alone"


def test_the_grammar_admits_and_refuses_each_shape() -> None:
    for s in GOOD:
        assert registry_id.REGISTRY_ID.fullmatch(s), f"{s!r} refused"
    for s in BAD:
        assert not registry_id.REGISTRY_ID.fullmatch(s), f"{s!r} admitted"


def test_the_three_consumers_hold_the_one_pattern() -> None:
    # The jobs parts load the file by path, so the object is a twin; the pattern text is what must be one.
    for owner, pattern in (("control/jobs.py", control_jobs.PROJECT_SLUG), ("jobs.py", jobs_tool.PROJECT_SLUG),
                           ("gzcoord/intake.py", intake.PROJECT_SLUG)):
        assert pattern.pattern == registry_id.REGISTRY_ID.pattern and pattern.flags == registry_id.REGISTRY_ID.flags, owner


def test_jobs_add_checks_a_dotted_project_and_refuses_a_bad_one() -> None:
    assert control_jobs.check_job_args({"title": "x", "project": "gzapi.ge"}) is None
    assert "registry id" in (control_jobs.check_job_args({"title": "x", "project": "gzapi..ge"}) or "")
    # js.string(1.5) is "1.5": a number reads as its text, as the contract in control/jobs.py says.
    assert control_jobs.check_job_args({"title": "x", "project": 1.5}) is None


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok   {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

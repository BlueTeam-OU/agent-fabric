#!/usr/bin/env python3
"""tools/fabric/lint_rules/card.py: a project's .agent-fabric/review-card.md within tools/fabric/review_card.py's CARD_CAP (j475).

Stdlib only; runnable as `python3 tests/test_lint_review_card.py`. Each case builds a throwaway agent-fabric root with tests/test_lint.py's
make_base and runs lint on it. **Each names the mutation it kills**:

  project_card_over_cap_is_labelled <- review_card_findings not wired into lint.main; the working copies not walked; the label dropped
  card_at_cap_passes                <- `>=` for `>`
  fabric_card_is_judged             <- only the working copies judged, not the fabric's own card
  no_card_is_no_finding             <- a missing card reported
"""
from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile

from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
from test_lint import PROJECT, make_base, run_lint, wc_demo, write  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "fabric"))
import review_card  # noqa: E402

TMP = tempfile.mkdtemp(prefix="lint-card-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

CAP = review_card.CARD_CAP
HEAD = "the project review card is"


def hits(out: str) -> list[str]:
    return [line.strip() for line in out.splitlines() if HEAD in line]


def fresh() -> str:
    return make_base(tempfile.mkdtemp(dir=TMP))


def case_project_card_over_cap_is_labelled() -> None:
    fabric = fresh()
    write(os.path.join(wc_demo(fabric), review_card.CARD_PATH), "x" * (CAP + 1))
    code, out = run_lint(fabric)
    want = f"{PROJECT}:{review_card.CARD_PATH}: the project review card is {CAP + 1} bytes, over the {CAP}-byte cap; shorten it"
    assert code == 1 and want in hits(out), out


def case_card_at_cap_passes() -> None:
    fabric = fresh()
    write(os.path.join(wc_demo(fabric), review_card.CARD_PATH), "x" * CAP)
    code, out = run_lint(fabric)
    assert hits(out) == [], out


def case_fabric_card_is_judged() -> None:
    fabric = fresh()
    write(os.path.join(fabric, review_card.CARD_PATH), "x" * (CAP + 1))
    code, out = run_lint(fabric)
    assert code == 1 and any(h.startswith(f"{review_card.CARD_PATH}: ") for h in hits(out)), out


def case_no_card_is_no_finding() -> None:
    code, out = run_lint(fresh())
    assert hits(out) == [], out


CASES = [case_project_card_over_cap_is_labelled, case_card_at_cap_passes, case_fabric_card_is_judged, case_no_card_is_no_finding]


def main() -> int:
    failures = 0
    for case in CASES:
        try:
            case()
            print(f"  ok   {case.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

---
role: "python-dev"
class: workflow
topic: "load-flake-count-before-after-and-resend-moves-counts"
description: "how j67 made timing-bound suites load-robust: pinned-core burners, a state cap instead of wall bounds, counts keyed to the message under test"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ab18d1d2f2f8e4eb
---

## how j67 made timing-bound suites load-robust: pinned-core burners, a state cap instead of wall bounds, counts keyed to the message under test

Method that worked (PR 374): reproduce with `taskset -c 3` plus 20 busy-loop
burners (`bash -c 'while :; do :; done'`) on a host whose load is already 45;
run each failing case 5 times on the tree before and after (a case filter
script for CASES-list suites; the whole suite for one without) and keep the
red counts per case for the PR body.

Two causes covered every red: (1) a wall bound sized for an idle interpreter
start, replaced by waiting on the state with a cap only a hang reaches
(90 s) and a wall bound that says its margin in the assertion; (2) a running
total or row count that a resend of another message moves, replaced by a
count for the message under test, read before and after.

**Why:** a reviewer found two bounds left in cases the PR already edited;
sweep the whole case for every wall bound, not only the failing line.
**How to apply:** after a fix, grep the edited cases for remaining
`time.monotonic() +` and `< N` bounds; plant one mutation per case.
Never `sleep N` then check in the harness: use a background until-loop.

*Anchors: `tests/test_gzcoord_protocol.py::STATE_WAIT_CAP_S`*

*Observed 2026-10-25 (python-dev)*

---
role: "flutter-dev"
class: workflow
topic: "red-check-outside-the-range-is-rerun"
description: "A PR's gate is red on a test the range does not touch, byte-identical to main and green there — re-run the failed job, never push a fix onto the PR; a head-scoped arm word survives a re-run, not a push"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5e6209896f52359d
---

## A PR's gate is red on a test the range does not touch, byte-identical to main and green there — re-run the failed job, never push a fix onto the PR; a head-scoped arm word survives a re-run, not a push

A ready PR's gate goes red on one test that sits in a file and subject the
range does not touch. The arming authority's decision on such a case: check that
the test file is byte-identical to main and that main's last run of that job is
green; then it is timing, not the change. Re-run only the failed job
(`gh run rerun <run-id> --failed`) and arm once it is green. Do not push to the
PR for it. If it fails a second time, it is a flake to fix on its own branch,
not on this PR.

**Why:** an arm authorization below the work-commit minimum (an `AUTHORIZES:
<repo>#<pr>@<sha>` DECISION) names one head. A re-run keeps that head, so the
word still holds. A pushed "fix", even a retry tweak, moves the head, voids
the word, and mixes an unrelated change into the PR's one change.

**How to apply:** before touching a red PR, ask `git diff origin/main..<head>
-- <failing test file>`: is it empty, and does the range touch the code under
test? If the diff is empty and the range does not touch that code, re-run. Say in the arm basis
or the PR thread which test flaked and that it was re-run. A second red sends
the flake to its owner's branch or a job of your own. Related:
[[a-green-check-is-evidence-only-once-seen-red]].

**The other branch of the test: the diff is NOT empty because main moved.**
When the world changed under the test (a runner image swapped coreutils;
the calendar crossed a DST boundary) and the fix landed in the test on
main, the PR still runs its own branch's stale copy: a re-run reproduces
the red every time. Then fold instead: `git merge --no-ff origin/main`,
push, and arm again — the push moves the head, so a head-scoped word is
void and a new one is needed. Seen twice in one night on gzapp (ban-checks
via 9c1db28b5; status_web zone test via 17be7e300), both broadcast as
"not your diff, fold main".

*References: a-green-check-is-evidence-only-once-seen-red*

*Anchors: `tools/fabric/github/arm.py::AUTHORIZES`*

*Observed 2026-10-23 (flutter-dev)*

---
role: "python-dev"
class: solution
topic: "j81-rereview-chain-needs-source-without-pr"
description: "j81 — chaining `fabric-review next` from a derived request that names pr is refused by resolve_range; no-checkpoint case; job-copy hook traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4d5e3880f579150c
---

## j81 — chaining `fabric-review next` from a derived request that names pr is refused by resolve_range; no-checkpoint case; job-copy hook traps

j81 (2026-10-23): test_review_rounds.py had its fake gh already (j80); added the no-checkpoint case
(`next --pr 7` with nothing served -> "render a full review") on `for/user/j333-review-coverage`, e520bd1c.

- A derived REQUEST-rrN.json carries `pr`; `next` validated it as a source, and review_brief.resolve_range
  then demands range base == the PR's last v2 review head, which is that very round. Chaining was refused
  until the coordinator validated the source without pr (590564a5, on their side). `--report` and `--pr`
  are mutually exclusive on `next`.
- A mutation of the new case: serving a v2 review in place of none must fail it (it does).
- Hook traps: a commit/push from another job's worktree is refused (ADR-037 rule 3), and so is any
  command containing `$HOME` or other expansions next to git commit/push; use literal paths, split
  the test run from the push, apply a saved diff in the job's own worktree.
- run.sh's `FAILED` greps hit fixtures (test_reads_live inside test_stripped_run); map failures to
  suites with an awk over the `== tests/...` headings before naming one.

*Anchors: `tools/fabric/review_rounds.py::next_request`*

*Observed 2026-10-23 (python-dev)*

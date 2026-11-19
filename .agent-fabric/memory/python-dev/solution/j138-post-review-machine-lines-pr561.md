---
role: "python-dev"
class: solution
topic: "j138-post-review-machine-lines-pr561"
description: "j138 PR 561 — post-review refuses unparsable Finding:/Judgement: lines; circular-import trap, fabric-review next recipe, boundary arm rule, suite flakes"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fc47b909aa8e4eb1
---

## j138 PR 561 — post-review refuses unparsable Finding:/Judgement: lines; circular-import trap, fabric-review next recipe, boundary arm rule, suite flakes

PR 561 (branch `develop-qzapp/python-dev-02/feat/j138-post-review-refuses-a-report-whose`): `fabric-pr post-review` reads the report with `errors.parse_machine_lines(body, whole=True)` before posting and refuses (exit 2, nothing posted, every malformed line named, shapes from `review_lines`). Reason: a posted review cannot be withdrawn and `arm_findings.py` treats an unparsed body as unread, so gzapp#1246 was stuck.

- `errors` imports `github.post_review` for REVIEW_MARKER, so post_review imports `errors` lazily inside `machine_lines_refusal` (a top-level import is a cycle).
- Only post_review passes `whole=True`; arm_findings, review_calibration and errors itself keep the default (names at most 5 lines, cut at 120 chars).
- Every existing test posting a body without machine lines needed `Finding: none` (`invoke(..., machine=True)`).
- Recipe for a re-review round: `fabric-review next <prev-request.json> --pr N --head <FULL 40-char sha>` (run from the clone, absolute path to the request; needs `save` first), dispatch code-review on fable, post bare `fabric-pr post-review N --model fable < report`.
- Merging origin/main changes the head and voids the review: a merge-only range needs its own re-review round (clean, quick).
- Security-boundary change under 8 work commits arms only on the owner's word or a coordinator REPLY with `AUTHORIZES: <repo>#<n>@<head>`; the word names a head, so a later merge voids it.
- Full-suite flakes seen: `test_control_agentd`, `test_jobs_switch` fail in a full run, pass alone.

**Why:** keeps the next session from rediscovering the cycle and the review-round mechanics.
**How to apply:** touching post_review/errors imports, or carrying a PR through re-review rounds.

*Anchors: `tools/fabric/github/post_review.py::machine_lines_refusal`, `tools/fabric/errors.py::parse_machine_lines`*

*Observed 2026-11-12 (python-dev)*

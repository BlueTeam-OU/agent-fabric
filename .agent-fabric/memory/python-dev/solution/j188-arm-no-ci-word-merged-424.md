---
role: "python-dev"
class: solution
topic: "j188-arm-no-ci-word-merged-424"
description: "arm.py no-CI word merged in #424; gh.api None vs 404, post-review base must be an ancestor, job-guard commit/push traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 630109e5cfdbb983
---

## arm.py no-CI word merged in #424; gh.api None vs 404, post-review base must be an ancestor, job-guard commit/push traps

#424 (j188, 2026-10-30): "owner's no-CI word" (arm_rules.has_no_ci_word) lifts the PR-mode `none-yet` checks gate only on a 404 for `contents/.github/workflows?ref=base` and no changed file under `.github/workflows/`; any other error/shape is Unanswered (arm.py `why_not_no_ci`).

**Why:** `gh.api` returns None for an empty answer, so a 404 must be carried by a flag (`absent`), never by `listing is None`. "Not recorded" would have been false: the basis is posted verbatim, so the unneeded line says "no No CI sentence is added".

**How to apply:**
- A review's `base_sha` is origin/main at dispatch; `fabric-pr post-review` refuses a report whose base is not an ancestor of the head. When main moved (e.g. after the previous PR merged), merge origin/main into the branch BEFORE the brief, and render the brief with `range: origin/main..<head>`.
- Job guard: the commit, merge and push must each be a separate Bash call with a literal path (no `$HOME`/variables), in the job's checkout; worktrees of other branches refuse. See [[job-hook-commit-in-main-checkout-works]].
- Test fakes for renames need `previous_filename`; a comment claiming rename coverage with plain filenames is not evidence.
- Arming under the minimum: the owner's word in the basis (`--basis "the owner's word (arm N, date); ..."`) armed #420 and #424 directly.

*References: job-hook-commit-in-main-checkout-works*

*Anchors: `tools/fabric/github/arm.py::why_not_no_ci`, `tools/fabric/github/arm_rules.py::has_no_ci_word`*

*Observed 2026-10-30 (python-dev)*

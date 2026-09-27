---
role: "fabric-coordinator"
class: workflow
topic: "check-exit-status-not-pipe"
description: "Never `check | tail -1 && git commit`: the pipe's status is tail's, so a failed lint/static/suite still commits — run the check, capture rc=$?, commit only on 0"
tier: 1
knowledge_scope: full
distilled_at: "2026-09-27"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 1fa68092e771d363
  - 770bfec8bc900afd
  - aeae47e1bf226620
---

## Never `check | tail -1 && git commit`: the pipe's status is tail's, so a failed lint/static/suite still commits — run the check, capture rc=$?, commit only on 0

Twice on 2026-09-25 a check failed and the commit went ahead anyway:
`python3 tools/fabric/lint.py 2>&1 | tail -1 && … git commit` (PR #35 opened
with lint red: the hosts schema refused operator_key) and
`bash tests/static.sh 2>&1 | tail -1 && git add … && git commit` (a
`.pathname` module URL the static guard forbids). The pipe's exit status is
`tail`'s, always 0. [[cross-repo-lint-window]] already said "no pipe before
the commit &&"; it was not enough as a clause inside another memory.

A third time the same day, a different shape: `…; bash tests/static.sh | tail -1;
git add … && git status; git commit` — the check ran, printed FAILED, and the
`;` after it let the commit go (unpushed, amended). The rule is not "no pipe"
but "the commit is gated on the check's own status in the same command".

**How to apply:** `bash tests/static.sh >/dev/null 2>&1; rc=$?; [ $rc -eq 0 ] && git commit …`
— every commit command, even a "small" one after a multi-step edit
— or `set -o pipefail` in the same command. Show the output separately if
it is needed. A test suite's summary line is read, not trusted by `&&`.

Fourth time, 2026-09-26: `a; b; c && git commit --amend` ran the amend on
static's status while test_fabric-status had just failed (`;`, not `&&`).
Caught before push, and re-amended gated on `rc`. Put the commit under
`if [ $rc -eq 0 ]` on the one check that matters, never behind a list
of `;`-joined checks.

Fifth occurrence, 2026-09-26, and not a commit: arming. On #49 I ran
`pr-gate.sh 49 | tail -1; gh pr comment …; gh pr merge 49 --auto` in one
command. The gate printed "BLOCKED: 1 unresolved thread" and the merge
went ahead anyway (a codex P2 on the pre-fix head, already fixed by the
merged commit — luck, not the gate). **The same rule for the arm:** read
the gate's verdict line and arm only on "MERGEABLE", in a separate step
after reading it; never chain `gh pr merge` after the gate in one command.

Sixth occurrence, 2026-09-27 on #51: `python3 tests/test_adr.py | tail -1 && git add … && git commit … && git push` committed and PUSHED 4480b2a with 31/32. Prose has not held six times: the fix is a guard, queued in [[next-fabric-branch-queue]] — a PreToolUse Bash hook that refuses a command where a pipe into tail/head/grep precedes `&& git commit` or `&& git push`.

*References: cross-repo-lint-window, next-fabric-branch-queue*

*Observed 2026-09-25 (fabric-coordinator)*

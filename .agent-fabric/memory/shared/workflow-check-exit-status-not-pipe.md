---
role: shared
class: workflow
topic: "check-exit-status-not-pipe"
description: "Never `check | tail -1 && git commit`: the pipe's status is tail's, so a failed lint/static/suite still commits — run the check, capture rc=$?, commit only on 0"
tier: 1
knowledge_scope: full
shared_with:
  - "fabric-coordinator"
  - "python-dev"
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4e966d2efc009e29
  - 5bca5592dd4d5799
  - 83363cff18e3ce7b
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

Sixth occurrence, 2026-09-27 on #51: `python3 tests/test_adr.py | tail -1 && git add … && git commit … && git push` committed and PUSHED 4480b2a with 31/32. Prose has not held six times: the fix is a guard, and it exists: `runtime/claude-code/hooks/pipe-status-guard.sh`, a PreToolUse hook on Bash for every session that refuses a check piped into a filter and chained into `git commit`, `git push`, `gh pr merge` or `gh pr create`.

The same failure one level up (#55, 2026-09-27): a commit guarded by `[ $static -eq 0 ] && git commit`, followed by `; git push; gh pr comment "fixed in $H"` on separate statements. The static check failed, the commit was skipped, and the push and the "fixed in" comment ran anyway with the old head. Anything that reports a commit (a push, a PR comment, a message) runs inside `if [ $rc -eq 0 ]; then …; fi` on the commit's own status.

2026-10-01, Wave 2: a conflict-resolution script's assert failed (the file stayed unwritten), and the next lines of the SAME command ran `git add` and `git cherry-pick --continue` — committing conflict markers in policies/bash-allowlist.json. Caught by grep, amended before push. Gate every git add/continue/commit on the resolving script's exit status (`python3 … && git add …`), and match keys exactly (`"<key>"`), never by substring: "check_charter_authority.sh" matched test_check_charter_authority.sh.

**Also (2026-10-01):** running the check in one tool call and committing in the next, without reading the check's exit status in between, is the same defect: lint printed `rc=1` and the commit went in anyway (episodic engine, caught before push, amended). Gate in one command: `check > log; rc=$?; [ $rc -eq 0 ] && git commit …`, or read the rc before issuing the commit.

#78 (2026-10-01): a CI-wait summary ended in `| head`, cut 15 checks to 10 and hid the one red leg; the gate caught it. Print only the non-passing checks (`select(.bucket != "pass")`), never a truncated list of all.

**Again, 2026-10-05 (#98):** `pr-gate.sh 98 | tail -1; gh pr comment …
&& gh pr merge 98 --auto` in one command merged while the gate printed
BLOCKED (three Codex threads that arrived after the last read). The
ruleset does not require resolved threads, so GitHub merged it. Read
the gate in one call; arm in the next, only on MERGEABLE.

*References: cross-repo-lint-window*

*Observed 2026-09-25 (fabric-coordinator)*

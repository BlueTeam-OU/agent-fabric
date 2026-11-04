---
role: "python-dev"
class: solution
topic: "job-copy-guard-command-words-j76"
description: "j76 (#348 r6 F8/F9): how the job-copy guard decides a dot/expansion runs a heredoc body; delivery as patch + for/ branch; the guard blocks your own push after a delivered job"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 23c6505d56d32762
---

## j76 (#348 r6 F8/F9): how the job-copy guard decides a dot/expansion runs a heredoc body; delivery as patch + for/ branch; the guard blocks your own push after a delivered job

job-copy-guard.py `runs_stdin` uses `command_words()` (command position after assignments, redirections incl. split `2>&1`, keywords, LAUNCHERS table) instead of judging by the previous word; a `.`/`$X` is a runner only as a command name. Launchers outside the table (flock, ssh...) are not followed. Mutations that proved the tests: argument positions as commands, timeout operand count, sudo `-u`, the `2>&1` skip, fused value options, assignment skip. Redirect-operand skip is where #354 later found P1s (`>(`/`<(`, `function f {`, `coproc`).

Delivery for a never-list file: commit tests on `.../for/user/<what>`, leave the guard change uncommitted, send `git diff` in the REPLY, and PUSH the branch before replying (the coordinator checks ls-remote). Push needs `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push`.

**Why:** once a job is delivered the guard denies `git push` in the same session ("worked a job, none active"); `fabric-jobs start <same id>` re-activates it for a finish-up push, then deliver again. `fabric-jobs switch` also refuses on uncommitted files, an unanswered REPLY-EXPECTED, and no memory change.
**How to apply:** push before `deliver`; run full `tests/run.sh` knowing test_gzcoord_protocol times out under another agent's concurrent run (passes alone).

*Observed 2026-10-22 (python-dev)*

---
role: "fabric-coordinator"
class: workflow
topic: "readded-job-check-tree-first"
description: "A re-added or carried-over job may already be delivered (another job, or its own merged PR never recorded); read origin/main and the jobs it spawned before starting it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3a7903f227e47f35
  - 6bed1ac24f1a9f9d
---

## A re-added or carried-over job may already be delivered (another job, or its own merged PR never recorded); read origin/main and the jobs it spawned before starting it

j195 (re-added 2026-10-14 as j89's replacement, "Record: reflection pass over episodic.db") was
already delivered when its session started 2026-10-15: ADR-058 accepted and on origin/main
(06612ee2, ac8a6cf5), `fabric-reflect` built in #264, its build remainder already queued as j215,
and the "upkeep survey" half had become ADR-050 (accepted 2026-10-13, build in j196). The job was
still marked blocked on its request to python-dev-02 although that request was answered (#256
closed, folded into #264).

Second case, 2026-10-19: j263 (InterWeave #286 round-8 findings + 293494a2) was handed to a fresh
session as active, with a new empty worktree, though all of it had merged as InterWeave #294 on
2026-10-17 and its follow-up was already queued as j265. The job had never been delivered, so
`switch` kept reopening it. The check took three reads: the PR list on the project's repo, the
PR body's ranges, and a grep of origin/main for each finding's fix.

Third case, 2026-10-20: j314 (arm #335, register fabric-gh-ledger, correct two slices) reached a
fresh session as active. All three were done: registration a353f8f9 inside #335, AUTHORIZES
01a158f0 sent, #335 merged 10:53, both source memories corrected at 12:26 (the slices follow at the
next drain). The job had only been blocked on the PR, never delivered. The check took one call:
`gh pr view <N> --json state,mergedAt` + `git log -S` on the artifact. Then `fabric-jobs deliver
<job> <PR> <message-id>` + `fabric-jobs sweep` closes it.

Fourth case, 2026-10-22: j285 (arming authorities, queued since 2026-10-19) was handed to a
fresh session as active on the open PR #356's branch. Every part had landed on 2026-10-19:
bcebf357 (ADR-019 rule 4, team.md, pull-requests skill), both architect-cto remits, the j161
settings PRs (BlueTeam-OU #9, gzapi-org #8), and the "it is live" INFO 01a15428. The job had
never been started, so nothing marked it. Fastest check: `git grep` origin/main for the job's
key phrase, then `fabric-history --since <job created> <phrase>` for the message step.

Fifth case, 2026-10-28: j448 (architect-cto-01's REQUEST 01a18168-0ae7: the sweep should
delete the login's own merged origin branches) arrived blocked on #416, which was the same
feature from my own earlier REQUEST 01a18168-d6a3 to python-dev-03, merged 10:37Z. A job
blocked on a PR whose title matches the job is likely answered by it: `gh pr view <N>` first;
the answer is a REPLY citing the PR, then `fabric-jobs done`.

Sixth case, 2026-10-30: j414 (ADR-029 rule 12's InterWeave budgets behind the code) was
blocked on #429 and handed to a fresh session after #429 merged. #429 had carried the amendment
itself (27a4ac64). Fastest check: import `control.carrier_install` (from `tools/fabric`,
`PYTHONPATH=.:..`) for the budgets, compare with the record's figures, `git log -S` one figure.
A job blocked on a merged PR of my own takes `fabric-jobs done`, not `deliver`: switch refuses
a delivered job whose PR is merged.

Seventh case, 2026-10-30: j415 (#390 live collection for python-dev-02's REQUEST 01a179d5)
was handed to a fresh session as active, though its REPLY 01a179d6 with both outputs had gone
out 2026-10-26 four minutes after #390 merged. One call found it: `fabric-history --thread
<request id>` lists the outgoing REPLY. Closing took `fabric-jobs deliver <job> reply:<id> <PR>`:
a bare `done` is refused until it names an artifact.

Eighth case, 2026-10-31: j477 ("identity.py's hold comment claims the session-start hook reads
the hold: build it or correct the comment, in #429") was opened 2026-10-30 15:32Z, while #429 was
still open. 19 minutes later #429's own commit 108188cd built the read (`hold_of` in
`runtime/claude-code/hooks/session-start.py`, tested by `test_hook_says_the_fleet_hold`), so the
comment was already true. A job filed against a finding on an open PR can be answered by that
PR's later commits: `git log -S'<symbol>' origin/main -- <file>` with the time it landed, against
the job's `created`. Then run the one test file and `fabric-jobs done <job> --no-artifact "<sha>"`.

**Why:** a re-added job keeps its old title, not the progress made under other jobs since; working
it from the title duplicates landed work.
**How to apply:** before starting a re-added or long-blocked job, `git log origin/main` for its
topic, read the thread it blocks on (`fabric-history --thread <id>`), and grep `fabric-jobs list
--all` for successor jobs; if it has landed, close it with the commit as evidence and take the
next. Related: [[memory-work-closed-2026-10-14]].

*References: memory-work-closed-2026-10-14*

*Anchors: `docs/adr/ADR-058-reflection-pass-over-the-journal.md::Accepted`, `bin/fabric-jobs`*

*Observed 2026-10-31 (fabric-coordinator)*

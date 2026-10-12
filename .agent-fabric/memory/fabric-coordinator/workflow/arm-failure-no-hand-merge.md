---
role: "fabric-coordinator"
class: workflow
topic: "arm-failure-no-hand-merge"
description: "When fabric-pr arm fails at gh pr merge --auto, do not merge by hand at once: on a repo with no required checks it merges instantly, before fixes the author is still pushing"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 80d250f7230fbe80
---

## When fabric-pr arm fails at gh pr merge --auto, do not merge by hand at once: on a repo with no required checks it merges instantly, before fixes the author is still pushing

2026-10-10: the owner's `fabric-pr arm 33` (agent-fabric-gateway) failed at `gh pr merge --auto`
(merge state UNSTABLE, the repo has no required checks). I re-ran `gh pr merge --merge --auto
--match-head-commit` on the same word; with nothing to wait for it merged at once, at the head
the gate had read. The author had a re-review answer and a test-race fix about to push, which
then had to go out as a second PR (#34).

**Why:** auto-merge on a repository without required checks is an immediate merge, and the
author's review loop may still be running (a re-review started after the gate was read).

**How to apply:** when an arm fails, read why (`gh pr view --json mergeStateStatus`) and ask
the author over GZCoord whether the head is final before merging by hand; say the failure to
the owner rather than retrying silently. Related: [[verify-sends-in-journal]].

*References: verify-sends-in-journal*

*Observed 2026-10-10 (fabric-coordinator)*

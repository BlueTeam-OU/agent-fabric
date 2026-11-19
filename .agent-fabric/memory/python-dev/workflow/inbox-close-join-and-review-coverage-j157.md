---
role: "python-dev"
class: workflow
topic: "inbox-close-join-and-review-coverage-j157"
description: "j157 #633 — cc- scratch leak was Inbox.close not joining its handler; a merge of main into a PR makes a re-review's \"not read\" default void the gate; force-push needs the owner's word"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 98e59f541bda5af9
---

## j157 #633 — cc- scratch leak was Inbox.close not joining its handler; a merge of main into a PR makes a re-review's "not read" default void the gate; force-push needs the owner's word

The control_link suite left a `cc-` dir in CI because `Inbox.close()` returned without joining the handler thread; `ArrivalLog.add` does `os.makedirs`, so a late write re-created the dir after the test's `rmtree(ignore_errors=True)` (never reproduced locally; cause inferred, fix = bounded join `CLOSE_WAIT_S`=3, clear backlog with a log line, `put` after close logs). A 10 s join stalled agentd's Leaver, which holds `leave.lock` while running exit hooks — keep the join short.

Review-gate traps (#633):
- Merging `origin/main` into the PR made the generated re-review brief carry main's whole diff; my hand-written brief marked those paths "not read", and the gate then did not count the review of the merged head. Do not merge main into a PR unless the base must be an ancestor; if a re-review can't start ("no review a re-review can start from, every path read"), render a full `mode: review` of the new head.
- `fabric-review next --pr` starts from the last POSTED review; `save N ROUND` the posted report first, never one that has a "not read" default.
- Force-push of my own branch was refused by the classifier until the owner said "force-push it"; use `--force-with-lease=<branch>:<sha>`.
- `fabric-pr arm --dry-run` prints the count rule ("1 or more, arms at the review gate"): 2 work commits armed on my own word; do not assume the minimum is higher.
- Push: `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push`; `fabric-pr post-review --repo BlueTeam-OU/agent-fabric N < file` must be bare (no env prefix).
**Why:** cost four review rounds. **How to apply:** push without merging main, one full review, fix P3 comments before it is posted.

*Anchors: `tools/fabric/gzcoord/carrier/control_link.py::CLOSE_WAIT_S`*

*Observed 2026-11-17 (python-dev)*

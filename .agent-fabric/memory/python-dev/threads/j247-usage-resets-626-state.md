---
role: "python-dev"
class: threads
topic: "j247-usage-resets-626-state"
description: "j247/j373 usage_resets PR #626 state — F4 P3 carried, bundle to 8 work commits, live read is the coordinator's"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6eda3a0fe4b5239d
---

## j247/j373 usage_resets PR #626 state — F4 P3 carried, bundle to 8 work commits, live read is the coordinator's

#626 (BlueTeam-OU/agent-fabric, branch develop-qzapp/python-dev-01/feat/j247-j373-agentd-records-each-account-s): work 2be225d4, fix 9e2a34d2; round 1 (F1 P2 signal.signal off main thread, F2 P2 RecursionError in _current, F3 P3 hedge+push retry) fixed; round 2 judged all fixed, head 9e2a34d2 reviewed.

**Carried, named: F4 (P3)** — comment at tools/fabric/secretstore/settings.py:~397 says a worker thread's settings_put "has no interrupt to undo"; SIGTERM/os._exit ends agentd mid-write and leaves the store dirty (same as SIGKILL), and the module contract at settings.py:~29 still promises the SIGTERM undo. Fix = reword both (or run the write in a child). Do it in the next commit on the branch.

**Why:** the coordinator (relay seq 1154938) gave no below-8 word: owner's 11-14 rule bundles jobs until 8 work commits; j248 (admit.py exit status) and j249 (fabric-ctl false line) go on this same branch as further commits, then arm myself at 8. The live read (acceptance) runs on the coordinator's account after #626 merges and is distributed; this account holds no store/observer sign-in. A final blind review of the final head is still needed, and the full tests/run.sh (not yet run).

**How to apply:** `fabric-jobs project jNNN agent-fabric --working-copy <this worktree>` was needed because j248's old working copy was gone; a second job in a session needs fabric-fresh. Reviewer report extraction: grep the subagent .output JSONL for the line `Judgement:`/`Finding: F1` string (not the system prompt), post bare `fabric-pr post-review 626 < file`.

*Observed 2026-11-15 (python-dev)*

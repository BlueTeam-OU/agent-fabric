---
role: "python-dev"
class: solution
topic: "harness-restart-marker-j112"
description: "j112 #478 harness-restart: one-shot resume marker design, review findings, arming at 1 work commit needs a coordinator AUTHORIZES"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6323b64c90a086fd
---

## j112 #478 harness-restart: one-shot resume marker design, review findings, arming at 1 work commit needs a coordinator AUTHORIZES

`fabric-ctl <login|all> harness-restart` (#478): the account itself writes `~/.local/state/agent-fabric/agents/<login>/harness-resume` (`harness_pane.py mark-resume` through `sudo -n -u`), path from the passwd home, never HOME/XDG (writer under sudo, reader under the user manager). `ensure` types `--resume` for a fresh (<600 s), regular, own-uid marker, then removes it; anything else is `--wait`.

Review lessons (round 1): (F1 P2) a failed restart must drop the marker again (`drop-resume`) or a later crash restart resumes; (F2) an unreadable or unremovable marker entry must degrade to `--wait` with a note, never fail ExecStartPost (crash loop); (F3) test the foreign-uid and future-mtime guards by mocking `os.getuid`/mtime. A header comment that says "a failed step keeps it" goes stale once the verb drops it: fix comments in the same commit.

Arming: 1 work commit on a boundary change is refused; ask the coordinator holder for a REPLY with `AUTHORIZES: <repo>#<n>@<head8>`, pass its id with `--authorization`; a doc-only fix after the word needs a new word. After `fabric-jobs deliver`, the hook blocks `fabric-pr arm`: add an arm job first (`fabric-jobs add`), then `switch`.

**Why:** cost two extra review rounds and an arm detour. **How to apply:** write the cleanup-on-failure and degrade-to-old-behaviour paths before the first review; add the arm job before delivering.

j113: #478 armed with `--authorization <REPLY id>` plus a basis naming "the owner's word" and the counts; it merged at once on head f46b34b3 (1 work, 2 fix), then an INFO to TO-ROLE fabric-coordinator for the upgrade. `fabric-jobs deliver` wants `reply:<id>` or a branch for a merged PR, not `pr:`.

*Anchors: `tools/fabric/control/harness_restart.py`, `tools/fabric/control/harness_pane.py`*

*Observed 2026-11-04 (python-dev)*

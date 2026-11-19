---
role: "python-dev"
class: workflow
topic: "j130-relay-log-journal-handoff"
description: "j130/j686 relay bridge.log bound — unit goes to the journal; unit and doc are outside python-dev's entry, so they travel as a HANDOFF diff"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 99f497a1f456245e
---

## j130/j686 relay bridge.log bound — unit goes to the journal; unit and doc are outside python-dev's entry, so they travel as a HANDOFF diff

j130 (owner's j686): gzcoord-relay.service appended to an unrotated bridge.log (1.64 GB). Chosen: StandardOutput/StandardError=journal. Branch for/user/j686-relay-log-bound head 436f2525 holds only the suite case (tests/test_gzcoord_protocol.py); the unit and BRIDGE-RELAY-SETUP.md diff went by HANDOFF 01a1bfcc-c428-75cf-a170-0f0a7b887763, because the commit hook refuses both even on a for/ branch (see [[never-list-files-go-as-handoff-patch]]).

**Why:** the hook draws the line by the entry, not by the request's "commit on your for/ branch".
**How to apply:** `git add` of everything before the refused commit stages the refused files too: stage only the entry's paths, save the patch from `git diff --cached`, then restore. The growth rate could not be measured: the log lives in the operator's account, unreadable here, and the classifier denies a /home/* glob. A full tests/run.sh once failed test_jobs_switch ("memory directory has not changed") and passed alone: session-state dependence.

*References: never-list-files-go-as-handoff-patch*

*Observed 2026-11-09 (python-dev)*

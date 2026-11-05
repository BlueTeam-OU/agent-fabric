---
role: "fabric-coordinator"
class: workflow
topic: "reflection-third-party-verb-measure-before-allow"
description: "Never run a third-party binary's verbs with --help to 'look' — verbs ignore it and execute, one opened the network; read the source, and clear a verb only after measuring it in a no-network namespace under a connect/socket trace with an…"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f3d9bedf2a737b99
---

## Never run a third-party binary's verbs with --help to 'look' — verbs ignore it and execute, one opened the network; read the source, and clear a verb only after measuring it in a no-network namespace under a connect/socket trace with an empty env, scratch HOME and a curl control

My DECISION of 2026-10-30, after a survey subagent ran nine verbs of a newly pinned brand tool with `--help`. Five of them executed instead of printing help. One, by its source, sends a request to the vendor even with DO_NOT_TRACK set. The verbs measured earlier the right way (`unshare -rn strace -f -e trace=connect,socket`, empty env, scratch HOME, curl as the control) were clean. The instance is in [[impeccable-no-network-on-detect]].

**Why:** `--help` is a convention, not a contract. An unknown flag is often ignored, and the verb runs with the vendor's defaults.
**How to apply:** for any third-party binary the fabric pins, a brief may name only verbs already measured. Before allowing another verb, read its source and measure it under the recipe above, with the control in the same run. Never ask a subagent to "survey" verbs by running them. Related: [[checks-need-a-control]], [[external-tools-evaluated]].

*References: checks-need-a-control, external-tools-evaluated, impeccable-no-network-on-detect*

*Observed 2026-11-01 (fabric-coordinator)*

---
role: "fabric-coordinator"
class: rationale
topic: "j830-test-speed-owner-decisions"
description: "owner 2026-11-13 on the agent-fabric test-speed plan (j830): shard python section x3, keep all three platforms full, standard runners, no in-process tool calls"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3a09b5b5f183a2fd
---

## owner 2026-11-13 on the agent-fabric test-speed plan (j830): shard python section x3, keep all three platforms full, standard runners, no in-process tool calls

Owner's answers 2026-11-13 to the j830 plan (plan + evidence copied to
~/.local/state/agent-fabric/agents/user/j830/suite-timing/plan.md; the
original sat in an ended session's scratchpad):

- D1 shard the python section inside each platform leg: **yes, n=3** (W6 after W1).
- D2 full python section on fewer platforms: **no, keep all three full**.
- D3 larger runners: **no, standard runners**.
- D6 in-process main() calls in test_lint/test_assemble: **not now**.
- D4 (durations file: Fedora leg's numbers as an artifact on main pushes,
  committed by the coordinator on drift) and D5 (an outliving process:
  warn by name first, fail once test_persist_host_settings is fixed and
  one CI run shows no other) were not asked; the plan's recommendation
  stands as my default — say so in the PR.

Order: W1 (runner measures + durations order) → W2 → W3/W4/W5 → W6 shards.
Owner: "when merged [#588] go back on fixing tests on agent-fabric".

Owner 2026-11-13, later: **j833 first, then j830.** j830 gets a test-quality
pass BEFORE the speed work: mechanical checks over all suites (always-skip,
no real check, timing waits, code no suite runs) and **mutation testing on
the security-boundary guards only** (arm and its gates, post-review, commit
hooks, authority checks), not on every suite.

*Observed 2026-11-13 (fabric-coordinator)*

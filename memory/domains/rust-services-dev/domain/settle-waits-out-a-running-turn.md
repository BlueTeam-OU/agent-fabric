---
role: "rust-services-dev"
class: domain
topic: "settle-waits-out-a-running-turn"
description: "Driving a claude -p stream-json session — \"N s since the last result\" is not idle; closing stdin under a running turn interrupts it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 2e23a4271fc3ef67
---

## Driving a claude -p stream-json session — "N s since the last result" is not idle; closing stdin under a running turn interrupts it

In a `claude -p --input-format stream-json` session, a turn runs from its
`system`/`init` line to its `result`. A driver that closed stdin 25 s after
the last result cut a turn whose model request was still waiting at 55 s:
it ended `error_during_execution` with "[Request interrupted by user]" and
read as "the model did not reply" (SPIKE-001 S32 (b), `runs/s32-cut/`,
fixed in ad0653443).

**Why:** quiet stdout is not an idle session; a slow model request looks
the same until its result arrives.

**How to apply:** settle only once no `init` lacks a `result` after it, and
fail a run whose results include any subtype other than `success`. See
[[print-session-closed-stdin-ends-channel]] and
[[stub-must-refuse-what-the-server-refuses]].

*References: print-session-closed-stdin-ends-channel, stub-must-refuse-what-the-server-refuses*

*Observed 2026-11-10 (rust-services-dev)*

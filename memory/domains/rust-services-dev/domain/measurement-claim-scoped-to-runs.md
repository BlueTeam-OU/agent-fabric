---
role: "rust-services-dev"
class: domain
topic: "measurement-claim-scoped-to-runs"
description: "Reporting a spike or live measurement: one run is that run's outcome, not a rule; an unreproduced cause is inferred; 'no log line' means none among the patterns searched; unrecorded conditions are named"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 931dfd1016b10693
---

## Reporting a spike or live measurement: one run is that run's outcome, not a rule; an unreproduced cause is inferred; 'no log line' means none among the patterns searched; unrecorded conditions are named

Each review of InterWeave's SPIKE-001 measurement PRs (#420 S23/S24, #427 S25) found
the same overreach. My write-up and its derived documents claimed more than the runs
showed:
- A cause was stated as measured, but it came from runs under conditions the new runs
  did not reproduce. S24 claimed why fact 4 failed, but fact 4 ran on another build,
  with another server shape, in plain -p. It could only be "consistent with".
- An ambient condition went unrecorded. Only one of eight runs recorded its permission
  mode, yet the facts were written as if the mode were known.
- One run was written as a rule. "Closing stdin ends nothing the session owes" came
  from the single run b.
- A silence was stated as absolute. "Logs nothing" really meant "no refusal among the
  four patterns the driver searched; the bridge's own log not captured".

The fix had to reach every site that restated the fact: README summary, correction
entry, SPIKES.md heading, INSTALL.md, the architecture docs and the plan. Fixing only
the cited line left the same class in summaries (two more commits on #427).

**How to apply:** before a measurement REPLY or a README fact goes out:
- Each claim names its runs.
- A claim from one run reads "in the one run that ...".
- A cause goes under Inferred unless a run changed only that variable.
- A negative names what was captured and searched.
- The driver records every ambient setting a reviewer could ask about (build,
  permission mode, flags, settings source) in the run record.
- When a fact is corrected, grep every document that restates it in the same commit.

*Observed 2026-10-25 (rust-services-dev)*

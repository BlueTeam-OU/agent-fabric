---
role: "fabric-coordinator"
class: threads
topic: "j378-rule13-waits-on-tag"
description: "ADR-064 carrier deploy pieces are on #371; only rule 13's two-account live run is left, and it waits on j401's release.json pin"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8e796f4423d492ea
---

## ADR-064 carrier deploy pieces are on #371; only rule 13's two-account live run is left, and it waits on j401's release.json pin

2026-10-25: python-dev-02's j379 patches (commands.json gzcoord-carrier + not_allowed, docs/live-checks/2026-10-24-interweave-carrier.md, CARRIER-CONTRACT enc/sender) landed on #371 as 7d73fb92, 886c66e1, 6bf72ab0. #365 and #373 merged. What is left of j378 is item 4: the two-account run (tests/live_interweave_two_accounts.py phases init/roster/serve/exchange/portcheck/stop), run on my own build of InterWeave compared with python-dev-02's SHA256SUMS, never its binary. v0.1.0 was published 2026-10-25T11:48Z (run 40179792207 attempt 2; Linux archive sha256 77fcc622…5115, read back from the page). ADR-064 §5 rule 4 pins only a published release, so j401 pins release.json first and the run uses the released build, not a checkout build. The live-check page gets the run's figures afterwards.

**Why:** the full suite was red 3 suites under load ~78 (gzcoord_protocol, carrier_engine, shim); all passed alone; see [[load-flake-briefs]].
**How to apply:** j378 is blocked on job:user/j401 (the pin); ask python-dev-02 for the runner at a host scratch path and read it whole first.

*References: load-flake-briefs*

*Observed 2026-10-25 (fabric-coordinator)*

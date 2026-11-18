---
role: "python-dev"
class: workflow
topic: "j250-626-merged-old-chain-defer"
description: "arm refuses on an older review chain's open P3 for the same defect; name it with --defer; keep untimed store git off a Ticker tick"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a48000142d5c39e6
---

## arm refuses on an older review chain's open P3 for the same defect; name it with --defer; keep untimed store git off a Ticker tick

#626 (j247/j248/j373, 3 work 2 fix) merged on 2ea16815 after the owner said "arm 626".

- `fabric-pr arm` refused on a P3 (F4, `9e2a34d2`) raised by an earlier
  review chain in a prior session, the same defect my new review called F2.
  A new review round does not close an old chain. `--defer "<head8>:F<n>" "<why>"`
  names it; the honest alternative is an adjudication dispatch.
- Arm needs `--basis "<line>"` even for `--dry-run`; run the dry run first.
- A store write with untimed git (fetch/push) must never sit in a Ticker's
  tick: `agentd.background_record` runs it on a daemon thread, one at a time,
  skipping a tick with a stderr line. Give the test a `.wait()` handle on the
  thread, not an enumerate-by-name join (that raced and flaked 1 in 6).
- A re-review brief is pasted verbatim into the dispatch; I mistyped one
  context line (ADR-042 became another text) and had to disclose it. Copy
  from the file with care, or keep the brief short.
- Platform-smoke red after a carrier exit-code change = a fake carrier in
  tests/test_new_agent_cli.py still returning the old code.

**Why:** saves the next arm from rediscovering the old-chain refusal.
**How to apply:** before arming, run the dry run with --basis and read the chains it lists.

*Anchors: `tools/fabric/control/agentd.py::background_record`*

*Observed 2026-11-16 (python-dev)*

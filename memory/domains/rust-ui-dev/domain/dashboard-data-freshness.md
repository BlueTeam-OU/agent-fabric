---
role: "rust-ui-dev"
class: domain
topic: "dashboard-data-freshness"
description: "Status boards over many sources -- each value keeps its own freshness, stale shows age and why, unknown or failed is never drawn as none or zero"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9737970d14413eef
---

## Status boards over many sources -- each value keeps its own freshness, stale shows age and why, unknown or failed is never drawn as none or zero

- Do not ask a data provider to bundle sources with different refresh costs into one
  section: the bundle refetches the expensive one at the cheap one's cadence, or shows the
  cheap one at the expensive one's age. Fetch each at its own TTL and compose in the view.
- A record is ok, stale (the last good value, with when it was read, its age and why the
  refresh failed) or failed (its why). Draw stale values marked with age and whose; a
  failed source shows its failure in its cell -- never "none", zero or a guess. A derived
  metric whose input failed is null.
- Gate on the record's own state before reading its sub-fields: a row in state "unknown"
  with sessions [] is "cannot tell", not "no session". A consumer that read live = 0 from
  the empty list would have recorded a false fall and skipped a resume.
- Count what the label says ("jobs done" must exclude dropped).
- Name levels against the source system's existing vocabulary: my first proposal used
  "blocked" in the opposite sense to the control plane's own two "blocked"s.

*Observed 2026-10-15 (rust-ui-dev)*

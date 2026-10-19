---
role: "devex-tooling"
class: workflow
topic: "presence-check-needs-content-evidence"
description: "a skip, \"already done\" or input-present check must test the content the step produces (non-empty file, the rows it fills), never a marker or path an older or other producer can leave"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a5b67843dba7c6c5
---

## a skip, "already done" or input-present check must test the content the step produces (non-empty file, the rows it fills), never a marker or path an older or other producer can leave

This extends the brief's "an empty local input is no input": what counts as present is the
content, not the name. Two gzapp stack cases, 2026-09-15/16: a nested file mount left a 0-byte
graph.obj on the host, and the resolver's "local file wins" check (`-f`) chose it over the
shared blob, so OTP failed to load (fixed with `test -s`, #735). The gtfs seed step was first
written to skip when the dataset version was active, but that version had been written by an
older importer, before the stop-search tables existed. A skip on the version would have kept
that broken database broken. #771 skips only when the version is active, the tables it fills
(gtfs_stop_lines) have rows for it, and a feasibility policy exists.

**How to apply:** when writing an idempotent step or an input resolver, name the artifact the step
produces and test for that artifact. A version row, a marker file, or a path that merely exists is
evidence only that something ran at some point, not that this step ran against today's schema.
Before trusting a skip condition, reproduce the broken state once (empty the tables, plant the
0-byte file) and check that the step does not skip.

*Observed 2026-10-16 (devex-tooling)*

---
role: "architect-cto"
class: solution
description: "InterWeave: a stage opened beside a lower one is opened by a plan-section record, never by the workspace status, which names the lowest open stage because three guards read it as a number; a deferral to the parallel stage never fires"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0af25148ae00e8e1
---

## InterWeave: a stage opened beside a lower one is opened by a plan-section record, never by the workspace status, which names the lowest open stage because three guards read it as a number; a deferral to the parallel stage never fires

`workspace.metadata.interweave.status` holds one value and names the
LOWEST open stage, because `check_stage_status.sh`,
`check_domain_fns_are_called.sh`'s deadlines and
`error_contract_matrix.rs`'s `open_stage` all read it as a number. A
second stage running beside it (Stage 16 beside Stage 15, 2026-10-03;
still recorded at plan lines ~4671 and ~4711 on origin/main as of
2026-10-15) is opened by writing its plan section in the standard stage
shape (objective, decided paragraph citing the owner's direction,
preconditions, batches with owners, suites, exit gate) with P0 reading
"opens beside Stage N on <prerequisite>; the status names the lowest open
stage; the new members join `[workspace].members` under this section, not
under the status". Two constraints follow: no `Proof::Stage(parallel)`
deferral in the error matrix while it runs beside the lower stage (it
would never fire, so it is not a deferral), and the Cargo.toml status
comment names both open stages. Code for the parallel stage waits for
that record AND its prerequisite spike's close, whichever is later; the
spike itself waits for nothing.

**Why:** the plan allows parallel workstreams once neutral contracts and
persistence are stable (ADR-0046 consequences); the status field is a
guard input, not the record of what is open.

**How to apply:** when asked "may stage N+1 open beside N", answer by the
record, keep the status at the lowest open stage until that stage's close
PR moves it, and write the deferral and status-comment constraints into
the new section's P0.

*Observed 2026-10-15 (architect-cto)*

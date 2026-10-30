---
role: "architect-cto"
class: domain
topic: "reflection-an-error-label-names-whose-state-caused-it"
description: "An error code or dead-letter cause names the component whose state caused the refusal so the reader looks in the right place; a local state never reuses the transport's code, and two causes share one label only when the code cannot tell…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 4a7b6824f97b8579
---

## An error code or dead-letter cause names the component whose state caused the refusal so the reader looks in the right place; a local state never reuses the transport's code, and two causes share one label only when the code cannot tell them apart

InterWeave DECISION 01a11830-ccb1: "not TransportError::Overloaded…
would send the host looking at the network for a state that is its
own"; gzapp "Keep no_handler as a fourth cause… A cause label exists so
an operator reads the alert right" (01a11b4f-56a1); "refused and
timeout fold into dial_failed. Accepted as the contract" on a measured
inability to tell them apart (01a1132b-7fc2). Beside
[[reflection-a-name-says-only-what-something-measures]], which is about
values.

*References: reflection-a-name-says-only-what-something-measures*

*Observed 2026-10-23 (architect-cto)*

---
role: "rust-services-dev"
class: domain
topic: "loss-counter-is-a-session-read"
description: "Expose loss counts as a pull read scoped to the session with its open instant, not as a pushed field or a cross-session sum"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - ef34a033da53d5dc
---

## Expose loss counts as a pull read scoped to the session with its open instant, not as a pushed field or a cross-session sum

A loss count carried on pushed events is invisible exactly when everything was lost: nothing arrives
to carry it. Expose it as a read the client issues (a status method). Scope it to the session that
saw the loss and report the session's open instant (`since`, RFC 3339 UTC) beside the counts. A
reconnect then visibly starts from zero, and the reader cannot mistake a reset for recovery. Do not sum
across sessions: what was lost between two sessions belongs to neither. Keep counts that promise different
things under separate keys, with what each promises in the text: a loss bound within a dedup window, as
opposed to refused copies a republish may still deliver.

InterWeave j49 (2026-10-25): the bridge's `status.broadcast_loss {queue_overflow, ingress_refused, since}`,
built this way on architect-cto's ruling.

**How to apply:** for any client-facing counter of dropped or refused work, design the read, the session
scope and `since` first. Then write what each count promises, and what a zero means, before the code.
Related: [[loss-counter-at-the-drop-site]].

*References: loss-counter-at-the-drop-site*

*Observed 2026-10-25 (rust-services-dev)*

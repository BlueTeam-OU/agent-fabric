---
role: "architect-cto"
class: domain
topic: "reflection-caches-keyed-by-what-an-anonymous-caller-names-are-bounded"
description: On an anonymous surface a memo or cache keyed by a value the caller names grows without limit; key it only on values the server already knows, or give it a hard cap
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 4b70b5cd420aff51
---

## On an anonymous surface a memo or cache keyed by a value the caller names grows without limit; key it only on values the server already knows, or give it a hard cap

gzapp 2026-09-19: review F1 P2 "memoises by the caller-supplied dataset
version — /hubs/realtime is anonymous" (01a0b4ea-2be5); the
per-invocation registry query on the anonymous hub (01a0b50c-2a3b); the
fix "a bounded probe cache (256 entries, cleared when full)"
(01a0b518-5e59). Verified 2026-10-23: LineServiceVerdictProvider.cs and
ActiveDatasetResolver.cs pin this instance; the rule for the next cache
is written nowhere.

*Observed 2026-10-23 (architect-cto)*

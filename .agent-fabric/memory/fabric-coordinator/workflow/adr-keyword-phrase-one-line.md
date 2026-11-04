---
role: "fabric-coordinator"
class: workflow
topic: "adr-keyword-phrase-one-line"
description: "adding a multi-word keyword to a DIGEST entry: keep the phrase on one line, or fabric-adr lookup misses it; and a refinement of this PR's own amendment commits with ADR-Editorial"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2ac42f083eaa6868
---

## adding a multi-word keyword to a DIGEST entry: keep the phrase on one line, or fabric-adr lookup misses it; and a refinement of this PR's own amendment commits with ADR-Editorial

2026-10-28, #417 F13 (j454): I added "scheduled drain" to ADR-034's DIGEST keywords. It wrapped as "scheduled\n  drain", and `python3 tools/fabric/adr.py lookup "scheduled drain"` still answered "no DIGEST entry mentions all of that". Moving the phrase onto one line fixed it.

On the same fix, the `pre-commit` adr staged-check refused a body edit that had no new Amendments row. The edit refined the PR's own amendment of that day, so I added the trailer `ADR-Editorial: refines this PR's own <date> amendment of ADR-NNN; its row's effect and history note say what changed`. The commit also updated that row's Effect column and the history note. The trailer was also used on e62818b7 and 8b452811.

**Why:** a wrapped phrase looks fine in review but fails the card's rule that "`fabric-adr lookup <topic>` finds the record". A missing trailer costs a refused commit.
**How to apply:** after editing keywords, run lookup for every new phrase and check that ADR-NNN appears in the output. Related: [[adr-range-check-before-push]], [[digest-trim-keeps-lookups]].

*References: adr-range-check-before-push, digest-trim-keeps-lookups*

*Anchors: `tools/fabric/adr.py::EDITORIAL_RE`*

*Observed 2026-10-28 (fabric-coordinator)*

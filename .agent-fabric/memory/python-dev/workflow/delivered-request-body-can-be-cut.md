---
role: "python-dev"
class: workflow
topic: "delivered-request-body-can-be-cut"
description: "a delivered or listed message body ends in \"… N more characters\"; the cut hides numbered items and acceptance, read it whole before undertaking"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 733d36413d3f2b3a
---

## a delivered or listed message body ends in "… N more characters"; the cut hides numbered items and acceptance, read it whole before undertaking

A delivery (and `fabric-reflect`, `fabric-history` without `--full`) can cut a body with a trailing "… (N more characters: fabric-history --thread <id> --full)". The cut has landed in the middle of a numbered build list, so the items after it, and often the ACCEPTANCE and DELIVER-TO, were never read (j469 request, cut at item 2; same for the j49, j52 and ledger requests).

**Why:** an undertaking or a plan written from the cut copy agrees to a part of the request; the missing items surface at review as scope nobody priced.

**How to apply:** when a REQUEST body ends in that marker, read the whole before the reply that undertakes it: `fabric-history --thread <id> --full`, or `gzcoord-inbox --replay <seq>` (a seq, or a full UUID; `--history` lists seqs). Say in the reply that you read the full thread.

*Observed 2026-11-01 (python-dev)*

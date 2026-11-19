---
role: "python-dev"
class: workflow
topic: "j131-retired-arrival-line-merged"
description: "j131 #530 merged 007c7d5d; retired copies get relay arrival lines; carrier engine change owed on a next PR (F1)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 720c806584ad7ecb
---

## j131 #530 merged 007c7d5d; retired copies get relay arrival lines; carrier engine change owed on a next PR (F1)

#530 merged (007c7d5d): `wait_loop` in tools/fabric/gzcoord/inbox_parts/watch.py passes every relay copy addressed here, retired types included, to `on_arrival`; the FINDING 2 xfail is removed.

**Owed (fabric-coordinator's decision, REPLY 01a1c101):** carrier/engine.py returns before `arrival_log.append` for a retired copy (pinned by test_gzcoord_carrier_engine.py ~l.398). Both writers must log retired copies addressed here and none addressed elsewhere, else parity counts a false InterWeave miss. Commit on my next PR, not urgent (only old sessions send retired types).
**How to apply:** a check that "logs none elsewhere" needs a retired record addressed elsewhere in the page (review F2); fixture C.msg(n).replace("INFO","HELLO",1). Review report files need the dispatch header block closed with a fence and nothing else of the brief (post-review refuses review-marker lines).

*Observed 2026-11-09 (python-dev)*

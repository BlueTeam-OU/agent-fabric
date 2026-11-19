---
role: "python-dev"
class: solution
topic: "j143-torn-line-final-lines-merged"
description: "j143 torn ledger tail: #576 merged; repair cuts a whole-JSON tail, final_lines must ignore it; test/CI traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3aa52f837dbc82e1
---

## j143 torn ledger tail: #576 merged; repair cuts a whole-JSON tail, final_lines must ignore it; test/CI traps

#576 merged 2026-11-13 (2 work, 0 fix; review and re-review "Finding: none"). `jsonl.repair` cuts any last line without a newline, even whole JSON; `ledger.final_lines` (LOCK_SH, no repair) read such a tail as a final line, so the carrier spool dropped an arrival the repaired ledger still owed its flagged re-show. Fix: `data.split(b"\n")[:-1]`. A torn final line in the ledger = pending without final = shown once more flagged "may repeat" (designed); torn pending = new; torn spool line = resend keeps it; acks/arrivals logs are evidence only. `tools/fabric/gzcoord/carrier/jsonl.py` docstring says so; `control/carrier_evidence.py` readers still count a bare whole-JSON tail (named there, not fixed).

**Traps:** `Spool.unseen` takes LOCK_SH on the ledger, so calling it after `Ledger.exclusive()` in the same process deadlocks (flock across two fds); call it before the lock, as watch.py does. A test that imports `test_gzcoord_carrier_inbox` creates the protocol suite's operator scratch at import and must remove `C.P.SCRATCH` itself, or run.sh reports "scratch left behind". CI debian platform-smoke failed once on `test_jobs_switch` "held: next is switch" (memory-dir check) and passed on rerun. SEMANTICS.md has no wording on "may repeat"; the owner was told, never edited. The post-review and arm commands are refused by the auto-mode classifier as self-approval until the owner says so in the conversation.

**How to apply:** a reader of a JSONL file that is not repaired counts only newline-terminated lines; mutation-check final_lines, repair and the shown-before decision against tests/test_gzcoord_carrier_torn_line.py.

*Anchors: `tools/fabric/gzcoord/carrier/ledger.py::final_lines`, `tools/fabric/gzcoord/carrier/jsonl.py::repair`*

*Observed 2026-11-13 (python-dev)*

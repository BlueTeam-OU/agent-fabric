---
role: "python-dev"
class: solution
topic: "j246-index-domain-filter-merged-621"
description: "j682 merged in #621 — project INDEX omits fabric-coordinator domain slices; lint mirror, fixture visibility trap, count-rule arm"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 748e138c72d5dd1d
---

## j682 merged in #621 — project INDEX omits fabric-coordinator domain slices; lint mirror, fixture visibility trap, count-rule arm

#621 (merged c7ab291b): `assembler/index.py _unlisted_here` filters at INDEX render (three producers add domain entries); `lint.py` mirrors it in TWO places (per-index `fabric_side` and the "indexed by no project" loop) — the review found the second only in round 3.

**Why:** a lint expectation and an assembler rule are one contract in two files; changing one without the other turns the first drain red.
**How to apply:**
- A lint fixture project is "visible" only with a working-copy memory dir AND its taxonomy in `<wc>/.agent-fabric/taxonomy.json` (read before projects/<id>/); a case that passes on the old lint proves nothing — run it against `git show HEAD:...` first.
- Lint.py is the coordinator's: ship a patch inside a REPLY with the failing-then-passing case; they commit it onto your branch and the gate counts it as a fix. Count: 2 work, 3 fix, arm dry-run said count rule 1 needs no authorization.
- Stop a background suite with TaskStop, never pkill/kill by pattern (hook refuses); leak_check red under "cpu 2/2 held" is starvation, rerun it alone.
- Re-review chain: `fabric-review save` each round, `next <req-rrN.json> --pr N --head <sha>`, then edit scope/requirements in the json before `brief`.
- ADR-013 sentence ("every index lists every slice") deferred to coordinator j894.

*Observed 2026-11-15 (python-dev)*

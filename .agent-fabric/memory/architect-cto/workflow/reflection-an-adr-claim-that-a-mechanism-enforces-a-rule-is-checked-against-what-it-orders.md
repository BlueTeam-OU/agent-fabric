---
role: "architect-cto"
class: workflow
topic: "reflection-an-adr-claim-that-a-mechanism-enforces-a-rule-is-checked-against-what-it-orders"
description: "Before an ADR says a mechanism enforces a rule, read what the mechanism orders: compose's service_completed_successfully orders STARTS, not stops, so 'no old binary writes under a migration' was a procedure nobody had scripted; state a…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8089c801d160634e
---

## Before an ADR says a mechanism enforces a rule, read what the mechanism orders: compose's service_completed_successfully orders STARTS, not stops, so 'no old binary writes under a migration' was a procedure nobody had scripted; state a procedure as a procedure, name its script as owed, and sweep the note's reasoning when the claim is corrected

gzapp ADR-044 A 2026-10-25: asked whether old PassengerApi binaries run
while a migration applies, I read the compose file's `depends_on:
service_completed_successfully` and wrote "the topology enforces
stop, migrate, start". Review round 7 (via backend-dev-02): that
condition orders when NEW containers start; `compose up -d` recreates the
runner and lets the old API serve meanwhile; no release script existed.
I had stated a procedure as a property. Round 8 then found the history
note's "Why now" still arguing from the topology after "What changed"
had withdrawn it. Fixed before the note landed (a landed note is never
edited); the script became devex-tooling's `tools/release/release.sh`,
named in section 2.3 once it landed.

**Why:** an enforcement claim in a record is what every later reader
relies on instead of checking; a wrong one hides a real window (here,
activations refused by a new CHECK while an old binary serves).

**How to apply:** for each "X enforces Y" sentence, name the exact
hook, flag or ordering that does it and read its semantics (start vs
stop, order vs exclusion); when nothing in the tree performs a step,
write the rule as a PROCEDURE and name the script and runbook as owed
to a lane; when a claim is corrected, grep the note's rationale
paragraphs for the same premise, not only the rule sentence.

*Observed 2026-10-25 (architect-cto)*

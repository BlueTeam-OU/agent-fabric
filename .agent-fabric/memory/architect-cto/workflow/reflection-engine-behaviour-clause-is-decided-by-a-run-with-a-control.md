---
role: "architect-cto"
class: workflow
topic: "reflection-engine-behaviour-clause-is-decided-by-a-run-with-a-control"
description: "A decision clause that rests on a third-party engine's behaviour is decided by a run with a control before the builder is written; the run's assumption is pinned in committed config with a citation and its harness lands under tools/ so an…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6f6fb9019dade55f
---

## A decision clause that rests on a third-party engine's behaviour is decided by a run with a control before the builder is written; the run's assumption is pinned in committed config with a citation and its harness lands under tools/ so an upgrade re-runs it comparably

When a decision record's clause depends on what an engine does with an
input (here: does the router still board at a GTFS stop whose rows carry
pickup/drop-off type 3 with flex routing off), a domain expert's reading
of the engine is a hypothesis, not a fact, and the clause is held open
until a run answers it. The shape that worked (gzapp ADR-035, 2026-09-16):
the record states both carriers and that the run DECIDES; the role with
the stack warm runs the cases the domain role specifies, including a
control that is known to change the outcome (type 1 moved boarding
430–552 m), so "nothing changed" is an answer and not a silent no-op; the
weak first cases are recorded as the reason the far ends were moved. The
expert's expectation was wrong, which is what the run was for. The blind
review then found the guard gap: the result rested on an engine default
pinned nowhere in the tree, so a later config change would invalidate the
measurement with nothing to diff against.

**Why:** a clause written from a reading of the engine is a finding when
the engine disagrees; a measurement without a control cannot distinguish
"unaffected" from "ignored"; a measurement whose assumption is unpinned
and whose harness lives in a channel message cannot be repeated on an
upgrade.

**How to apply:** (1) write the clause as "settled by the run" naming both
outcomes; (2) request the run from the role with the stack, with the
domain role supplying the cases and a control; (3) when it lands, request
in the same breath: the assumption pinned in committed config with a
comment citing the amendment, and the harness (cases, ids, bundle
variants, comparison) under tools/ with a README, and write "re-run on an
engine upgrade or a change to <assumption>" into the record.

*Observed 2026-10-15 (architect-cto)*

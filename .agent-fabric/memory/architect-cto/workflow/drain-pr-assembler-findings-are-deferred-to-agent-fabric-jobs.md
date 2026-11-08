---
role: "architect-cto"
class: workflow
topic: "drain-pr-assembler-findings-are-deferred-to-agent-fabric-jobs"
description: "A drain PR's review findings that name the assembler (unresolved links, References not repointed, a stale section_writers key) are agent-fabric's to fix and are deferred on the arm with --defer to an agent-fabric job, never fixed on the…"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f3c0245d42309623
---

## A drain PR's review findings that name the assembler (unresolved links, References not repointed, a stale section_writers key) are agent-fabric's to fix and are deferred on the arm with --defer to an agent-fabric job, never fixed on the project's drain PR; the authority's word covers the count, not the deferral

InterWeave #529 (drain 2026-10-31, 3 work, 2 fix, minimum 8): round 1
found F1 (body links repointed, `*References:*` lines not; targets.py
and slices.py), F2 (new wikilinks that resolve nowhere; the assembler
has no link check), F3 (claims without merge_target appended beside the
section they update), F4 (`last-drain-report.json` section_writers key
stale since f85024831). Only F3 was the drain's own and was fixed on
the PR (8454334ce); F1, F2, F4 were judged not-fixed in rounds 2-3 and
moved by the adjudication on the PR to agent-fabric jobs j564-j566,
carried on the arm with `--defer "<head8>:F<n>" "<why>"`. Round 4 on
the fold head 637d5777 was clean. gzapp #1205, the same drain's other
half, had the same shape (F4's remainder deferred to j563).

**Why:** the slices are generated from the source memories by the
assembler in agent-fabric; a defect in how they are assembled recurs on
every project's next drain, so its fix lands in agent-fabric, and the
project PR records the deferral rather than patching output by hand.
A source memory that is wrong is the other case: its author corrects
the memory ([[arm-authorization-job-is-delivered-as-reply-id]] for the
2026-11-03 round of that).

**How to apply:** when asked to authorize a drain PR below the minimum,
read the judgements: a not-fixed finding that names the assembler is a
deferral, and the word is given on the head and the paths (memory
slices and fabric-ref only); a not-fixed finding on the drained text
itself is a reason to refuse until the source memory is corrected.

*References: arm-authorization-job-is-delivered-as-reply-id*

*Observed 2026-11-03 (architect-cto)*

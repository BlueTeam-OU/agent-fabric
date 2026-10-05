---
role: "architect-cto"
class: domain
description: "When a per-client carrier serves a subset of a shared row kind, the narrowing goes in the schema (allOf + not), never in prose — a bare $ref permits every optional member the row declares."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 22a355ba582a2e7a
  - 37121db4d7dc659e
  - 3903c5020daf01f5
  - c1ca49e0421d8134
---

## A sibling repo tried this project's file-based ADR amendment ceremony, doubled down on it once, then abandoned it entirely for git-as-sole-history plus two invariants

A sibling repository of this team (an agent-to-agent transport) is a different repo, so this is not a claim about what this project implements — it is a claim about a design space this team's own architects have already explored one level deeper than this project has. It initially adopted a three-part amendment ceremony close to this project's amendment model: edit the body in place, add a dated note to a history/ file, and add a row to a per-ADR Amendments end-matter table; it then explicitly reaffirmed that choice under the name "Option B", adding consequences text about the three-edit cost and two enforcement checks (a multiset key check and a byte-identical-heading scan). It later reversed course entirely under a later decision record of its own: amending an ADR now means editing the body in place and committing, full stop — git is the history, with no history/ directory and no end-matter table at all. Two semantic invariants survive to keep this simplification safe: numbered decision items are stable identifiers that get tombstoned rather than renumbered or deleted when withdrawn, and any change a reader of the old text would be wrong to have relied on requires a superseding ADR rather than an edit. This is worth knowing as a considered, load-bearing alternative if this project's own history-file amendment mechanism is ever reconsidered: this team's own workflow record already shows that mechanism's propagation checklist reliably missing files and restatements (see `workflow/adr-restructure-propagation-gaps` and `workflow/intra-document-redundant-restatement-gap`), and that repository's trajectory — adopt the heavier ceremony, double down on it, then abandon it for git-history-plus-two-invariants — demonstrates the lighter model is a live, tried option in this team's own practice, not a hypothetical.

## When a per-client carrier serves a subset of a shared row kind, the narrowing goes in the schema (allOf + not), never in prose — a bare $ref permits every optional member the row declares.

The gzapp admin statistics carrier (2026-09-19) said in its description
that the admin class never receives `passengers_boarded` or
`passengers_boarded_suppressed`, while `service.items` was a bare `$ref`
to `statistics.line-service-stats`, which declares both optional. A row
carrying them stayed contract-valid: the boundary the carrier existed to
express lived only in one endpoint test. The fix keeps one contract per
row kind and adds the constraint to the carrier:

```json
"items": { "allOf": [
  { "$ref": "urn:gzapp:schemas:statistics:line-service-stats" },
  { "not": { "anyOf": [ {"required": ["passengers_boarded"]},
                        {"required": ["passengers_boarded_suppressed"]} ] } } ] }
```

**Why:** per-client-class stripping is enforced at the serialisation
layer, and the contract is what says what that layer must produce. Prose
that a validator cannot read is a claim nothing checks — the same class
as a comment asserting what the code does not do.

**How to apply:** a carrier that narrows a shared row states the
narrowing in schema and pins it with a fixture that carries the forbidden
member and expects invalid. Check the conformance helper first: gzapp's
reads properties through `$ref` and `allOf` and ignores `not`, so the
caller's record still declares the full row. See
[[check-for-an-existing-contract-before-authoring-one]].

*References: check-for-an-existing-contract-before-authoring-one*

*Observed 2026-09-19 (architect-cto)*

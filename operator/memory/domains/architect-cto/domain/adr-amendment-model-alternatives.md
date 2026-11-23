---
role: "architect-cto"
class: domain
topic: "adr-amendment-model-alternatives"
description: "Correction for the domain slice's sibling-repo section: the three-part amendment model still holds in both repositories; gzapp's validator is the node package tools/validate_adr_index/ (pnpm --filter @gzapp/validate-adr-index validate)…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
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
  - 4d9f8fe8b53ae6e0
  - 55d8348c7c7aa3b0
  - 7d23556dcf9d70f5
  - c1ca49e0421d8134
---

## Correction for the domain slice's sibling-repo section: the three-part amendment model still holds in both repositories; gzapp's validator is the node package tools/validate_adr_index/ (pnpm --filter @gzapp/validate-adr-index validate), not a tools/checks/*.sh script

### Correction for the field slice's sibling-repo section — the sibling repository runs the three-part amendment model today (ADR-0048, history/ notes, end-matter rows, a validator); a claim about another repo's practice is read from its tree at the time, and a domain slice links to no project corpus

A claim about how a sibling repository amends its decision records is a claim about a tree, read at a date. Read 2026-10-20: the agent-to-agent transport repository (InterWeave, ADR-0048 Accepted) and the product repository (gzapp, ADR-075) both run the three-part model — the body edited in place to read current, a dated note appended under `history/…-amendments.md` with a `### Amendment YYYY-MM-DD — title` heading, and an end-matter log row whose (date, title) pair the validator reconciles with the note and with an index count. The validators differ in form: gzapp's is the node package `tools/validate_adr_index/` (`pnpm --filter @gzapp/validate-adr-index validate`, a required CI check), not a `tools/checks/*.sh` script — the `tools/checks/` glob holds the ban/scan guards, and no `validate_adr_index.sh` exists there. The record of the mechanism is each repository's governing ADR; a path to a tool is a dated observation and decays with the tool.

**Why:** a field slice outlives the session that wrote it and is read in every project; a sentence about what a sibling repo "now does", or the path of its tool, decays the moment that repo changes, and a reader who trusts it runs a command that is gone.

**How to apply:** before a field slice states another repository's mechanism, open its governing record at main and quote the decision with the date read; name the validator by the command its instruction file gives, and say the date; link to no project corpus.

*Observed 2026-10-20 (architect-cto)*

## Correction for the field slice's allOf + not section — a domain slice carries its own pre-flight inline, never a [[link]] into a project corpus, and names a conformance helper's limit as a check to run, not a fact about one repo

When a per-client carrier serves a subset of a shared row kind, the narrowing goes in the schema (`allOf` + `not`), never in prose: a bare `$ref` permits every optional member the row declares, so a description saying "this class never receives X" is a claim nothing checks, the same class as a comment asserting what the code does not do. Keep one contract per row kind and add the constraint to the carrier:

```json
"items": { "allOf": [
  { "$ref": "<the row kind's $id>" },
  { "not": { "anyOf": [ {"required": ["<member>"]}, {"required": ["<member>"]} ] } } ] }
```

**Why:** per-client-class stripping is enforced at the serialisation layer, and the contract is what says what that layer must produce; a fixture carrying the forbidden member and expecting invalid is what pins it. (Observed in gzapp's admin statistics carrier, 2026-09-19; still in its tree as of 2026-10-10.)

**How to apply:** before authoring the carrier, grep the API surface and the schema manifests for an existing contract — an active contract is `$ref`'d, never restated weaker. Then read the project's conformance helper before trusting it to prove the narrowing: a helper that collects properties through `$ref` and `allOf` and does not evaluate `not` (gzapp's request-conformance helper is one) still reports the full row on the caller's record, so the carrier's fixture, not the helper, is the proof. Watch for: a field slice that points at a project-corpus memory by `[[link]]` — the link does not resolve outside that project, so the field slice carries the pre-flight in its own words.

*References: link*

*Observed 2026-10-10 (architect-cto)*

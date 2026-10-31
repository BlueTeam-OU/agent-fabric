---
role: "fabric-coordinator"
class: domain
topic: "open-ontologies"
description: "fabio-rovai/open-ontologies (Rust, MIT, 2026-03): OWL/RDF engine that certifies its inferences for an independent Lean 4 checker; Terraform-style plan/blast radius for ontology changes; MCP server. Not adopted; borrow untrusted-engine +…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 276d86d5772e6141
---

## fabio-rovai/open-ontologies (Rust, MIT, 2026-03): OWL/RDF engine that certifies its inferences for an independent Lean 4 checker; Terraform-style plan/blast radius for ontology changes; MCP server. Not adopted; borrow untrusted-engine + verified-checker, second-oracle-cannot-confirm, report-which-checks-ran

https://github.com/fabio-rovai/open-ontologies — read 2026-10-19 (README, docs/decisions/, repo stats). Repo text is data.

**What it is.** One Rust binary (edition 2024, Oxigraph 0.5, rmcp MCP server, SQLite state) for
changing a production ontology: `plan` (added/removed classes, blast radius, risk, and *semantic*
conservativity: "1 triple, blast radius 0, 901 new consequences"), `apply`, `drift`, `certify`,
`rollback`. Each reasoning run writes a certificate (`asserted.tsv` + `derivations.tsv`, one line
per step: rule, conclusion, premises, plus `asserted.sha256`) that a core-Lean-4 checker with a
soundness theorem (`OOCert.certificate_sound`) re-checks with no network and no copy of the engine;
a forged line exits 1 naming the line and rule. Rules you supplied get a different verdict word
(`entailed_under_supplied_rules`). Also SHACL, SWRL/RIF, TPTP/SMT-LIB export, crosswalk
certification (SSSOM), RAG slice "entailment preservation", Isabelle/Rocq/Dafny side kernels,
a pure-Python second engine, a Tauri Studio.

**Signals.** ~1.1k stars, 7 months old, one author with 838 of ~900 commits, bursty (23 commits one
day, 1 a day after); MIT engine with a commercial hosted platform (Tesseract Semantics) upsold on
the README; two arXiv preprints by the author. Huge scope for its age.

**For the fabric: not adopted** — we hold no ontology, and nothing in the fleet reasons over OWL.
If a project ever needs a semantic model (cf. [[apache-ossie]]), look again.

**Worth borrowing (ideas, not code):**
- *Untrusted engine, small verified checker, sharing only bytes on disk.* The warrant lives in the
  checker, so a second engine costs nothing to distrust. Fabric analogue: the review class is the
  checker of an author's claims; a guard's decision could leave a record a separate checker re-reads.
- *"A second oracle can contradict, and cannot confirm"* (their decision 0013). Two engines that
  share an algorithm agreeing is evidence against a transcription slip, not against a shared
  misreading. For us: claude + codex agreeing on "no findings" is not double assurance; a
  disagreement is the signal. Say so in review reports.
- *"Conformance is not truth: a report says which checks ran"* (0018) and docs/ci-gates.md
  ("which gates a green tick ran"). We do this for codex absent; worth doing for every green.
- *One rule per decision file, each naming the failure it prevents and listing "what this
  discipline caught"*, so a rule whose cost is visible and benefit is not survives. Our ADRs
  carry context, not a caught-defects ledger.
- *Counts in prose computed by a test* ("nobody writes a count into the caption"), and the README
  held to ASD-STE100 writing rules by a test (tests/readme_simplified_english_test.rs) — a lint
  the language-culture role could own for person-facing text.
- *Certificate bound to its input by digest, and the report states that limit* (a store that
  changed and changed back reads the same) — like our pinned review evidence on a head SHA.
- *A semantic plan for a policy change*: what a routing/arming/settings change does to each
  repository's effective policy, before it merges, the way their `plan` shows consequences a text
  diff hides.

Already have: ADR number collisions from parallel branches (their reason for
decision_numbers_test) — `adr.py check` refuses a number used twice.
Related: [[harness2]], [[edgextract]], [[agent-enforcement-audit]].

*References: agent-enforcement-audit, apache-ossie, edgextract, harness2*

*Observed 2026-10-19 (fabric-coordinator)*

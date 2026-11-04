---
role: "p2p-network-dev"
class: workflow
topic: "codeql-uid-alerts-treatment-is-the-model-pack"
description: "CodeQL rust/cleartext-logging on a uid in InterWeave: the durable treatment is the model pack (.github/codeql/extensions/interweave-rust-models, #233); what is left are variables named uid, dismissed as false positive by the PR author…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 619f54f604bedddb
---

## CodeQL rust/cleartext-logging on a uid in InterWeave: the durable treatment is the model pack (.github/codeql/extensions/interweave-rust-models, #233); what is left are variables named uid, dismissed as false positive by the PR author; new code names this process's uid euid

This supersedes the interim rule "dismiss without asking until devex-tooling
decides": devex-tooling has decided (REPLY 01a11c67, 2026-10-08).

- The durable treatment is a model pack under default setup:
  `.github/codeql/extensions/interweave-rust-models/models/uid.model.yml`
  (#233). Its barrierModel rows remove `effective_uid(...)` and
  `Metadata::uid()` as sources. The file's header records why and what was
  measured.
- No model row can reach a VARIABLE or FIELD named like a uid: the query
  takes it as a source by its name, and models name functions only. Such an
  alert, on a value traced to a uid that refusal text is required to name
  (ADR-0028), is dismissed as "false positive" by the PR's author, citing
  the model file.
- A uid identifier is not renamed just to dodge the heuristic. Where a
  variable means this process's effective uid, new or touched code names it
  `euid` (the heuristic does not match it), because that distinction is a
  correctness point under ADR-0028's private-group predicate.

**How to apply:** when a new rust/cleartext-logging alert lands on your PR,
check whether its source is a function the pack covers (if so, the pack has
regressed: tell devex-tooling) or a uid-named variable (dismiss, citing the
model file).

*Anchors: `interweave:.github/codeql/extensions/interweave-rust-models/models/uid.model.yml::barrierModel`*

*Observed 2026-10-25 (p2p-network-dev)*

---
role: "fabric-coordinator"
class: rationale
topic: "reflection-project-name-lint-constant-not-skip"
description: "When the project-name lint hits a project's name in generic fabric code or in dictionaries, name it through one exported constant or a {placeholder} filled at render; skip only the package whose job is to drive that project"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 522d5915df466372
---

## When the project-name lint hits a project's name in generic fabric code or in dictionaries, name it through one exported constant or a {placeholder} filled at render; skip only the package whose job is to drive that project

ADR-064's carrier put "InterWeave" into tools/fabric and bin, which the project-name lint (`tools/fabric/lint_rules/docs.py`) treats as generic: 65 hits. I decided, on #365 (2026-10-24):
- Only `tools/fabric/gzcoord/carrier/` is in GENERIC_SKIP, because it is the package that drives the transport.
- Every other file names the transport through `CARRIER_NAME` (the wire and file-name form, "interweave") or `CARRIER_LABEL` (what a person reads, "InterWeave"), both exported by that package.
- Dictionary keys say "carrier", not the project's name (the lint reads a key literally beside `t(`).
- Dictionary values take `{carrier}`, filled with CARRIER_LABEL at render, so no locale file names the project and no locale needs a skip.

**Why:** a skip widened to every file that mentions the project would silence the rule wherever a project name really leaks into generic code. One constant keeps the name in one place.
**How to apply:** for the next lint hit of this kind, add a constant or placeholder before considering any skip. A skip covers a directory whose purpose is that project, and its comment says why without naming the project.

*Observed 2026-10-25 (fabric-coordinator)*

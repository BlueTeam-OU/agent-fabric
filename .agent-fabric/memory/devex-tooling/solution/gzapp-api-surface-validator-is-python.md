---
role: "devex-tooling"
class: solution
topic: "gzapp-api-surface-validator-is-python"
description: gzapp tools/validate_api_surface is Python since Wave 10 — check 4 is jsonschema over a vendored OAS 3.1 schema; what differs from the Node one
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0040f677b611cf63
---

## gzapp tools/validate_api_surface is Python since Wave 10 — check 4 is jsonschema over a vendored OAS 3.1 schema; what differs from the Node one

Since ADR-040 Wave 10 (gzapi-org/gzapp#1126, 2026-10-19) `tools/validate_api_surface/`
is `validate.py` + `deprecated_refs.py` + `js_parity.py`, deps pinned in
`requirements.txt` (jsonschema 4.23.0, pyyaml 6.0.2 — the Fedora host's versions);
`_api-surface.yml` runs the modules directly with no Node/pnpm. Package scripts
(`validate`, `test:unit`, `check:deprecated-refs`) keep their names for humans.

Check 4 = `jsonschema.Draft202012Validator` over `schemas/openapi-3.1.schema.json`,
copied unchanged from @seriousme/openapi-schema-validator 2.11.0 (its $dynamicRefs
are plain $refs), with ajv-formats' full-mode `email`/`uri-reference` regexes and a
port of that package's `checkRefs`. Known differences, by design: an
`openapi-spec-invalid` detail lists jsonschema errors (not ajv's); an
`-unparseable` detail is Python's exception text; OpenAPI ≠ 3.1 is invalid until
its schema is vendored. Error lists are sorted by file (Node: glob walk order).

build-glyphs.mjs is exempt (fontnik: native Node addon, no Python binding, and
`--check` byte-compares committed SDF ranges) — coordinator accepted 2026-10-19.

*Anchors: `tools/validate_api_surface/validate.py::Draft202012Validator`, `tools/validate_api_surface/requirements.txt::jsonschema==4.23.0`*

*Observed 2026-10-19 (devex-tooling)*

---
role: "devex-tooling"
class: domain
topic: "node-yaml-port-needs-yaml12-loader"
description: "Porting a Node script that reads YAML with the `yaml` package to Python — PyYAML's default (1.1) reads documents differently; what to keep and how to prove it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d48c9c92e64231e1
---

## Porting a Node script that reads YAML with the `yaml` package to Python — PyYAML's default (1.1) reads documents differently; what to keep and how to prove it

A Node script using `yaml` v2 (`YAML.parse`) reads YAML 1.2 core schema; PyYAML's
`safe_load` reads 1.1. Differences that change a checker's answer: `on`/`yes` → True,
`017` → 15 (octal), dates → datetime, `<<` merges, duplicate keys silently last-wins
(yaml throws "Map keys must be unique", comparing by value: `true`/`True`, `1`/`1.0`
collide, `"200"`/`200` do not). JS objects also stringify keys (`200` → "200",
`~` → "") and order integer-like keys first — so a JSON pointer `#/…/responses/200`
only resolves if keys are stringified. Also JS truthiness (`get: {}` is truthy),
`\s` (U+FEFF yes, \x1c no), multiline `^`, `split("#")` destructuring, UTF-16 sort.

Fix used in gzapp's Wave 10 port (gzapi-org/gzapp#1126, `tools/validate_api_surface/js_parity.py`):
a `CSafeLoader` subclass with `yaml_implicit_resolvers = {}` re-added for the 1.2 core
regexes, own int/float/map constructors, merge/timestamp/binary refused. Base it on
`CSafeLoader`: the pure-Python parser made a reparse-per-$ref validator 16s vs 3.5s.

Proof that worked: run the old .mjs test unchanged against a shim that calls the
Python (only the import line differs), plus a differential over ~100 historical
trees comparing full outputs, plus a mutation corpus; and mutation-check the new
YAML cases by swapping in `yaml.safe_load` (6 fail). Node's own `node --test`
suites there leak `mkdtemp` sandboxes into $TMPDIR — clean after an oracle run.

*Observed 2026-10-19 (devex-tooling)*

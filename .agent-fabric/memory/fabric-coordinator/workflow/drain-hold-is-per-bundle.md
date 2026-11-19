---
role: "fabric-coordinator"
class: workflow
topic: "drain-hold-is-per-bundle"
description: "assemble.py --hold must name only slices of the bundle it runs on, and a held claim's watermark is per source, not per bundle"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: gzapi.brand
    working_copy: gzapi.brand
derived_from:
  - b15c0e7e7a8fd3ae
---

## assemble.py --hold must name only slices of the bundle it runs on, and a held claim's watermark is per source, not per bundle

Holding slices back in a drain with `tools/fabric/assemble.py --bundle … --hold <file.json>`
has two traps (seen 2026-11-09, gzapi.brand#14 commit 4da33ce):

1. `--hold` refuses (exit 1, "--hold names no slice of this drain") when the list names a slice
   from another bundle. Give each bundle its own hold file with only its own `role/class:topic` keys.
2. The report keeps one watermark per source (`<login>@<host>`), not per bundle. When one source
   has two bundles (two working copies), the held watermark stops short only of the latest claim.
   The earlier claim (its bundle's `next_watermark` is lower) is not harvested into that corpus
   again. Read each bundle's manifest `next_watermark` before claiming in a commit that a hold
   "comes back next drain".

**How to apply:** one hold file per bundle; before writing "the next drain takes it again",
compare each held claim's bundle `next_watermark` with the report's watermark for its source.
Related: [[one-job-guard-reads-whole-command]].

*References: one-job-guard-reads-whole-command*

*Anchors: `agent-fabric:tools/fabric/assemble.py::--hold names no slice of this drain`*

*Observed 2026-11-09 (fabric-coordinator)*

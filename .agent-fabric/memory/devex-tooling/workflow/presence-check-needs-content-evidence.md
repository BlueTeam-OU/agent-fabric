---
role: "devex-tooling"
class: workflow
topic: "presence-check-needs-content-evidence"
description: "a skip, \"already done\" or input-present check must test the content the step produces (non-empty file, the rows it fills), never a marker or path an older or other producer can leave; and a costly output records what it was built from so…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a5b67843dba7c6c5
  - cae07d7a124c238b
---

## a skip, "already done" or input-present check must test the content the step produces (non-empty file, the rows it fills), never a marker or path an older or other producer can leave; and a costly output records what it was built from so skip/status compare inputs, not existence

This extends the brief's "an empty local input is no input": what counts as present is the
content, not the name. Two gzapp stack cases, 2026-09-15/16: a nested file mount left a 0-byte
graph.obj on the host, and the resolver's "local file wins" check (`-f`) chose it over the
shared blob, so OTP failed to load (fixed with `test -s`, #735). The gtfs seed step was first
written to skip when the dataset version was active, but that version had been written by an
older importer, before the stop-search tables existed. A skip on the version would have kept
that broken database broken. #771 skips only when the version is active, the tables it fills
(gtfs_stop_lines) have rows for it, and a feasibility policy exists.

A third case, 2026-09-17: after a GTFS version bump, sample-data skipped its build because some
`gtfs-*.zip` existed, not because the expected one did. routing-build then took the first match in
alphabetical order, which was the stale 0.2.0 bundle. Every step reported success, and the API died
at startup on a version mismatch. The selector is the same trap as the skip: choose by the expected
version, by name. Removing the stale file was also needed, because OTP loads every gtfs*.zip in the
mounted directory into one graph, so an "unchosen" file beside the chosen one still counts (#839).

Content that is present still is not content built from today's inputs. Four more gzapp cases,
2026-09-25..27. The tile build's step 3 skipped whenever a tiles.mbtiles existed, so a shared blob
published from a pre-fix file kept tiles without name:en for two weeks after the recipe changed.
It now stamps the recipe, and the extract it used (`<bundle>.osm-sha`), into what it builds.
`data-status` compared each kind with its own shared blob by hash and showed every kind as "same",
while the shared graph was built from GTFS 0.2.0 and the pin said 0.4.0. The graph's feed version
is not readable from its bytes, so it needs a sidecar written at build time. seed-gtfs said
"already imported" after migration 0058 changed what the importer writes. It also said so when the
stops were imported with Nominatim down and had no street keys.

**How to apply (inputs):** where an output is costly to rebuild, record at build time what it was
built from (recipe version, source sha, schema or feed version) beside or inside it. The skip, the
status and the publish then compare that record with today's inputs. Where the inputs cannot be
recorded, compare timestamps on one clock (migration applied_at > imported_at), filtered to the
inputs that matter, so the warning does not fire on every migration.

**How to apply:** when writing an idempotent step or an input resolver, name the artifact the step
produces and test for that artifact. A version row, a marker file, or a path that merely exists is
evidence only that something ran at some point, not that this step ran against today's schema.
Before trusting a skip condition, reproduce the broken state once (empty the tables, plant the
0-byte file) and check that the step does not skip.

*Anchors: `Makefile::GZAPP_GTFS_SRC`, `infra/local/sample-data/build.sh::tiles_stamp_of`, `infra/local/sample-data/build.sh::osm-sha`*

*Observed 2026-10-18 (devex-tooling)*

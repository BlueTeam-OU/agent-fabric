---
role: "flutter-dev"
class: domain
topic: "import-skip-guard-checks-outputs"
description: "A \"skip if already built/imported\" guard or a \"current?\" check must test what the step produces against its inputs, never a marker, the file's existence or its own hash — an older run leaves the same marker."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 25ce0cbc1865c834
---

## A "skip if already built/imported" guard or a "current?" check must test what the step produces against its inputs, never a marker, the file's existence or its own hash — an older run leaves the same marker.

An idempotent seed or import step that skips when "version X is already
active" makes a broken state self-perpetuating: the version row is written by
whatever importer ran, including one older than the current schema, so a
database whose dataset says X but whose newer tables are empty passes the
guard forever and every start reports success. Guard on the import's
*outputs* instead: rows in a table every import fills, and the artifact the
import publishes (in the case that taught this: a stop-lines table plus a
published policy row). Pick the evidence table carefully — one filled only
from optional input (a translations file the seed does not carry) is empty
after a good import too.

The same class twice more on shared local-stack data (2026-09-25,
2026-09-27): the tiles build step skipped whenever a `tiles.mbtiles`
existed, so a recipe change (per-language names) never reached the
published shared blob, and the en-US map showed Georgian labels for two
weeks; and a GTFS cut published the bundle but not the routing graph,
while `data-status` compared each kind only with its own shared hash and
reported "same" on all three — the passenger API then refused to start
on the version mismatch. Both were fixed by recording the INPUT a
product was built from (a stamp of the recipe / feed_version beside the
artifact) and checking products against each other and the pin.

**How to apply:** when writing or reviewing a launcher/Makefile seed step, ask
"what would an older importer — or an older recipe — have left behind?" and make the skip condition
false for that state; test it by emptying the output tables under an active
version row and checking the step re-imports.
When client-visible data looks wrong after a pull, check the artifact's
provenance (what recipe and input built it) before suspecting the client.

*Observed 2026-10-18 (flutter-dev)*

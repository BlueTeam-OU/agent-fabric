---
role: shared
class: threads
topic: "suite-scratch-leak"
description: "tests/run.sh fails naming anything a run left under TMPDIR (since agent-fabric #26, 2026-09-20); node suites use tests/scratch.mjs, static.sh refuses inline mkdtempSync; never run the suite twice at once — the two share scratch and fail…"
tier: 2
knowledge_scope: full
shared_with:
  - "fabric-coordinator"
  - "python-dev"
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d1814b604dc786fb
---

## tests/run.sh fails naming anything a run left under TMPDIR (since agent-fabric #26, 2026-09-20); node suites use tests/scratch.mjs, static.sh refuses inline mkdtempSync; never run the suite twice at once — the two share scratch and fail each other

Measured 2026-09-20 on develop-qzapp: after one clean `tests/run.sh`
run, `/var/tmp/agent-fabric-user` held 72 new directories (~1.3 MB);
before cleaning it held 472 directories, 120 MB, accumulated over two
days of suite runs (and two runs I killed mid-way). The leakers by name:
`agentd-home-*`, `send-*`, `home-*`, `hold-*`, `fabric-*`,
`assemble-bundle-*`, `harvest-bundle-*`, `marp-cli-*`, `tmp*`.
`node-compile-cache` is a cache and stays.

**Why:** the owner's rule (2026-09-19) — a test run leaves behind nothing
it did not find. A killed run is the worst case, so never start the
suite while another is running: the two shared scratch and one reported
a failure the other had caused.

**Fixed in agent-fabric #26 (2026-09-20):** `tests/scratch.mjs` for every
node suite (removed at process exit), `atexit` on the two bundle dirs,
`TemporaryDirectory` in the review-brief suite; `tests/static.sh` refuses
inline `mkdtempSync` in a `*.test.mjs`, `tests/run.sh` lists TMPDIR before
and after and fails naming each new entry. **How to apply:** when run.sh
names a leftover, fix the suite that made it at the rule level (a helper
or an exit hook), not with a one-off `rm`. Never start the suite while
another run is going. Related: [[pr-band-accumulate]].

*References: pr-band-accumulate*

*Observed 2026-09-20 (fabric-coordinator)*

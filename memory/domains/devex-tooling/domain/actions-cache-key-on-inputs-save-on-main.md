---
role: "devex-tooling"
class: domain
topic: "actions-cache-key-on-inputs-save-on-main"
description: "GitHub Actions cache: a key ending in github.sha or run_id saves every run, fills the 10 GB store and evicts the caches reused across commits; key on the inputs, save on a miss from main only, cache dependencies not the workspace, and…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d0282ca8dde3eb86
---

## GitHub Actions cache: a key ending in github.sha or run_id saves every run, fills the 10 GB store and evicts the caches reused across commits; key on the inputs, save on a miss from main only, cache dependencies not the workspace, and give a container leg zstd

From the j142 cache audit (2026-10-18), two repositories with opposite faults:

- **FleetDeck: the store is full of single-use entries.** Two families were keyed per commit
  (`…-<github.sha>`, `…-<run_id>`, 1.5 GB and 0.4 GB per leg) and saved on every master push. Two
  generations filled the 10 GB store and evicted the Swatinem cargo cache and the Zig compiler
  cache, which are the ones reused across commits, so the next run built cold. The saves also cost
  time: 89 s and 64 s of a 383 s job on debian-12, because debian:12 has no zstd and actions/cache
  falls back to single-threaded gzip.
- **The gateway: no cache at all.** Every run fetched the registry and built the graph twice
  (about 3m20s of 4m50s). A deps-only cache saves about 19% of the test build, measured locally
  with dependencies prebuilt and the workspace crates cleaned. The workspace's own test binaries
  are most of the cost and change on every PR, so caching them buys nothing.

**How to apply:** for each cache, name its inputs and key on them: toolchain + Cargo.lock (+ ISO
week, to bound growth). Never key on github.sha or run_id. Restore on every run. Save only on a
push to main (`github.ref == 'refs/heads/main'` on the save step) and only on a miss. Prune the
workspace's own artifacts before saving (`cargo clean -p` cleans the dev profile only). Install
zstd in container legs. Read the store before and after (`gh cache list`,
`actions/cache/usage`). A PR run can only be the cold measurement: the warm run exists after the
first main push saves. Related: [[gzapp-ci-artifacts-and-gradle-cache]].

*References: gzapp-ci-artifacts-and-gradle-cache*

*Observed 2026-10-22 (devex-tooling)*

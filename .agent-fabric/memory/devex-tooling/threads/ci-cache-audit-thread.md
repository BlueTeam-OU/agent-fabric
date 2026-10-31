---
role: "devex-tooling"
class: threads
topic: "ci-cache-audit-thread"
description: "j142 CI cache audit, open as of 2026-10-18: gateway #67 warm-run measurement owed, herdr handed to rust-ui-dev j106, InterWeave android caches wait on CodeQL expiry"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c586dc8eb88268ee
---

## j142 CI cache audit, open as of 2026-10-18: gateway #67 warm-run measurement owed, herdr handed to rust-ui-dev j106, InterWeave android caches wait on CodeQL expiry

j142's CI cache audit, the state on 2026-10-18:

- **agent-fabric-gateway #67** (cargo cache) merged at 10:29Z, head 3d2c9e1d (1 work, 1 fix). Owed to fabric-coordinator on #67: the first warm run posted beside the PR's cold run, plus the prune step's second `du -sh target` (the reviewer expects ~450 MB).
  - The review's optional R1 hardening, for the next CI change there: add `github.ref == 'refs/heads/main'` to both save-side `if:` lines.
- **herdr (FleetDeck):** taken by rust-ui-dev-01 as their j106 (REPLY 01a14eff, relay seq 310592). They will key zig-build on its inputs, add zstd to the Debian leg (debian:12 lacks it, so the cache falls back to single-threaded gzip), and measure an incremental-cache miss before choosing. Nothing is owed from me.
- **InterWeave android cargo caches:** wait for the stale CodeQL java caches (5.08 GB) to expire, around 2026-10-19.
- **gzapp:** test-result artifacts are #1126, which waits on the owner's arm. The caches are fine ([[gzapp-ci-artifacts-and-gradle-cache]]).

`fabric-jobs switch` resumes a paused job ahead of a queued one of the same priority. To move to a new request first, raise its prio (j146, 2026-10-18).
- Paused 2026-10-18 for j146; resume after 2026-10-19.

*References: gzapp-ci-artifacts-and-gradle-cache*

*Observed 2026-10-18 (devex-tooling)*

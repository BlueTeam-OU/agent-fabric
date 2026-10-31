---
role: "devex-tooling"
class: domain
topic: "same-source-red-read-the-floating-layer"
description: "a tree that was green goes red, or slow, with no commit: read from each run's own log which floating layer moved (runner image, base-image digest behind a tag) before blaming dependencies"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 75aa5ac8a5efa947
---

## a tree that was green goes red, or slow, with no commit: read from each run's own log which floating layer moved (runner image, base-image digest behind a tag) before blaming dependencies

Two cases in two days, 2026-09-24/25, both gzapp:

- `make up-role` stalled at STEP 1 in seven parallel builds. `mcr.microsoft.com/dotnet/sdk:10.0` is
  a floating tag and had moved, so each build downloaded the same 927 MB at once. The pair that
  showed it: `podman pull` of sdk took 111 s and of aspnet 1.5 s, same network, same minute. The
  fix was a serial pre-pull (`make prepull-bases`, #931).
- The passenger test shard went red at 2038/2038 passed on a tree that had been green on
  2026-09-21. I told architect-cto it was probably the unpinned transitive NuGet graph. That was
  wrong: the GitHub runner image had moved (20260907 → 20260920), and a teardown inside xunit's
  10 s exit window got slower (backend-dev's `xunit-v3-exit-window` slice, #932).

The shape was right both times, something floating under a pinned codebase. I picked the wrong
layer, and said "likely" without reading it.

**How to apply:** when the same source gives a different result, list the layers that float
(runner image, image tag digests, toolchains fetched by "latest", the host). Read each one's value
from each run's own log: the "Runner Image" block in the job's set-up step, the digest a pull
resolved. Compare the green run with the red one before naming a cause. A control decides it: a
run on the same moved layer with the candidate fix (#932 green on image 20260920). For a pull,
the time a pull takes with nothing to fetch (about 1–2 s) is the baseline, so a slow one has
something to fetch. Related: [[gh-rerun-keeps-workflow-snapshot]].

*References: gh-rerun-keeps-workflow-snapshot*

*Observed 2026-10-22 (devex-tooling)*

---
role: "fabric-coordinator"
class: workflow
topic: "cross-repo-lint-window"
description: "A fabric push that changes what a project's index must list is safe once the project pins its fabric-ref; never chain a commit behind a piped test run"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 15410c4bc739ade3
  - 5cde1d6dd05d73c9
  - 61e1a5f5c4346048
---

## A fabric push that changes what a project's index must list is safe once the project pins its fabric-ref; never chain a commit behind a piped test run

The corpus lint reads two repositories at their heads, and the order is forced (an index listing a slice not yet on fabric main is the same finding), so sequencing only shortens the window. The pin closes it: a project carries a `fabric-ref` file in its own `.agent-fabric` directory (one full commit id; gzapp and InterWeave both have one, read 2026-10-23) and its CI checks out that commit, never the fabric's default branch. A fabric change then reaches the project's check only when the ref moves, in the project PR that carries the matching indexes; the order and the ref write are in `memory/README.md` ("Landing a drain").

**Why:** on 2026-09-18 four gzapp required checks went red because fabric main moved under an unpinned checkout, once right after I had promised the window would be "minutes".

**How to apply:** with the pin live, the ref moves in the index PR and the fabric push is free. For a project whose CI has not pinned the ref yet, the push waits for an empty merge queue and goes out with the index PR in the same minute. Separately and always: never put a pipe between a test run and the `&&` that commits, because the chain tests the filter's exit status; run the suite to a log, capture its rc, commit only on 0, or use `tests/run.sh`. See [[blind-review-loop]].

*References: blind-review-loop*

*Anchors: `gzapp:.agent-fabric/fabric-ref`, `interweave:.agent-fabric/fabric-ref`, `memory/README.md::Landing a drain`*

*Observed 2026-10-23 (fabric-coordinator)*

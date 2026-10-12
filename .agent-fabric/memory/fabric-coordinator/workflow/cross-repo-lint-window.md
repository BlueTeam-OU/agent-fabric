---
role: "fabric-coordinator"
class: workflow
topic: "cross-repo-lint-window"
description: "A fabric push that changes what a project's index must list is safe once the project pins .agent-fabric/fabric-ref; never chain a commit behind a piped test run"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-12"
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
  - 5cde1d6dd05d73c9
  - 61e1a5f5c4346048
---

## A fabric push that changes what a project's index must list is safe once the project pins .agent-fabric/fabric-ref; never chain a commit behind a piped test run

The window is closed where the pin is live. The corpus lint reads two repositories at their heads, and the order is forced (an index listing a slice not yet on fabric main is the same finding), so sequencing only shortens the window. The pin closes it: a project carries `.agent-fabric/fabric-ref` (one full commit id; present now in gzapp and InterWeave) and its CI checks out that commit, never the fabric's default branch. A fabric change then reaches the project's check only when the ref moves, in the project PR that carries the matching indexes; the order and the ref write are in `memory/README.md` ("Landing a drain").

**Why:** on 2026-09-18 four gzapp required checks went red because fabric main moved under an unpinned checkout, once right after I had promised the window would be "minutes". The CEO: "all time the same error ... did you learn?"

**How to apply:** with the pin live, the ref moves in the index PR and the fabric push is free. For a project whose CI has not pinned the ref yet, the push still waits for an empty merge queue and goes out with the index PR in the same minute; say it on the relay when a queue holds one longer. Separately and always: never put a pipe between a test run and the `&&` that commits, because the chain tests the filter's exit status and a commit once went to main with a failing case that way (the hook now refuses the shape); run the suite to a log, capture its rc, commit only on 0, or use `tests/run.sh`. See [[blind-review-loop]].

*References: blind-review-loop*

*Observed 2026-10-11 (fabric-coordinator)*

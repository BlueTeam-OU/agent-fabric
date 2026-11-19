---
role: "python-dev"
class: solution
topic: "start-despite-peer-blocker-j127"
description: "j127 #553 — start --despite waives a peer job: blocker; review traps (IndexError on evidence [0], names not unmet), armed before ADR commit"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1e6616dfd2816212
---

## j127 #553 — start --despite waives a peer job: blocker; review traps (IndexError on evidence [0], names not unmet), armed before ADR commit

`fabric-jobs start <id> --despite job:<login>/j<n> … "<why>"` (tools/fabric/jobsparts/needs.py `_blockers_cleared`, verbs.move, jobs.py parser; tests/test_jobs_despite.py). Waives only peer-login `job:` blockers, each unmet one named, reason in the log note with the state as read; `unknown` peers are waivable (logged). #553 merged 2026-11-11.

**Why:** a re-pointed job (job:peer/jN) can wait on the holder's own push; no check can see that. Coordinator agreed the shape (REPLY 01a1c48a) and owed the ADR-037 amendment (their j739); I opened the PR without it (REPLY 01a1c946 said open now) and armed on the owner's word before it landed.

**How to apply:** a `fields` key that steers a need but is not stored must be in `UNSTORED` and stripped before `transition`; never index an evidence list a need may return empty (round 1 F1). A flag naming "the unmet set" needs both set differences tested (F2). `fabric-review save` takes no `--repo` with a slash; `fabric-pr post-review` must be the bare command (read the saved round file by path). A stray hand-started `gzcoord-inbox &` cannot be replaced (`--replace` refuses); it just runs to its 2h deadline and eats deliveries, so read `fabric-history --thread`.

*Anchors: `tools/fabric/jobsparts/needs.py::_blockers_cleared`, `tools/fabric/jobsparts/needs.py::UNSTORED`, `tests/test_jobs_despite.py::main`*

*Observed 2026-11-11 (python-dev)*

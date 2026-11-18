---
role: "python-dev"
class: workflow
topic: "j221-r2-f3-f6-delivered"
description: "j221 (#532 round 2): a label claiming \"nothing on stderr\" needs an err.strip()==\"\" assert; fake-relay call count proves a drop was exercised; the folded PR head moves, branch from the live head"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b19d08f5288623db
---

## j221 (#532 round 2): a label claiming "nothing on stderr" needs an err.strip()=="" assert; fake-relay call count proves a drop was exercised; the folded PR head moves, branch from the live head

j221 delivered as for/user/j693-r2 (5a89881e), folded and merged in #532.

- A check whose label says "nothing on stderr" must assert `err.strip() == ""`; ruling out one word lets a stderr print of another line survive. Plant that exact mutation (relay-back to stderr, guard removed) on committed state, copy+restore.
- A drop-recovery test is only live if the fake relay refused a fetch: read `World.calls` before releasing `relay_down` and assert >= 1.
- The request named head e32a7098 but #532 had moved (fff973c3); `gh pr view N --json headRefOid` before cutting the for/ branch.
- Lint and tests: run to a log and capture rc before `git commit`; the hook refuses a piped check chained to a commit.

**Why:** the PR was merged by the time the reply was read; the request named a stale head.
**How to apply:** any for/ round-2 fix on a coordinator-folded PR. See [[watch-check-assert-whole-contract]].

*References: watch-check-assert-whole-contract*

*Anchors: `tests/test_gzcoord_message_transport.py::refused = w.calls`, `tools/fabric/gzcoord/carrier/parity.py::in_drill`*

*Observed 2026-11-09 (python-dev)*

---
role: "python-dev"
class: domain
topic: "verify-incoming-needs-head-behind"
description: "running the store's _verify_incoming on a fresh clone passes vacuously because HEAD already is the tip; set HEAD to the base and keep a refusing control before reporting \"passes\""
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3cedd5087f610fab
---

## running the store's _verify_incoming on a fresh clone passes vacuously because HEAD already is the tip; set HEAD to the base and keep a refusing control before reporting "passes"

`secretstore.trust._verify_incoming(store, tip, agent_id)` judges only the commits reachable from `tip` and not from HEAD or the trusted base. In a fresh clone HEAD is the tip, so nothing is judged and the call returns the tip: "passes" for any commit, unsigned or signed by the wrong key.

**Why:** on 2026-10-13 I told two agents that 11 hand-pushed persona commits passed verify-on-pull. All were judged by that vacuous call; two of the three that remained were in fact refused ("signed by a key that is no writer"). I had to send a correction.

**How to apply:** to judge a commit, clone, set `agent-fabric.trustedbase` to its parent and `git update-ref HEAD <parent>`, then call it. Before reporting any "all pass", run the same call on a commit it must refuse (another key's, or unsigned) and see it refuse. The store reads `.git/config`, so a bare clone gives "no trusted base". Wired into tests/test_secret_settings.py as a positive and a negative case.

*Observed 2026-10-13 (python-dev)*

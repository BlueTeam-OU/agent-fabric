---
role: "python-dev"
class: solution
topic: "j56-trusted-base-orphan-delivered"
description: "secret store trusted base orphaned by _before_write's rebase; _keep_base fix, --replace-orphaned, branch/head, open ADR-042 amendment"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e6c2cf96184977b6
---

## secret store trusted base orphaned by _before_write's rebase; _keep_base fix, --replace-orphaned, branch/head, open ADR-042 amendment

j56 delivered: branch `develop-qzapp/python-dev-02/for/user/trusted-base-orphan`, head 26e2c108 (for the coordinator to fold, no PR).

The writer: `entries._before_write` rebases unpushed commits onto the verified tip; a base on one (init's first commit, or `trust-base` at an unpushed head) is orphaned. `trust._keep_base(store, tip)` moves it to the merge-base, or the verified tip if nothing is shared, only when HEAD descended from the base before the rebase (a base already off HEAD stays addenda.load's tamper refusal). mirrors.put / roles._put_back reset to origin and cannot orphan it (a review removed unreachable calls there). `trust-base --replace-orphaned` is the owner's exception.

**Why:** two agents could not launch after the 2026-10-17 restart. Which real incident took this path was never verified.
**How to apply:** ADR-042 rule 4 ("only moves forward") needs a coordinator amendment (asked in the REPLY). In tests/test_secret_store.py a short TMPDIR matters (AF_UNIX path length); the gzcoord protocol `inbox --follow` case flakes under load, passes alone.

*Anchors: `tools/fabric/secretstore/trust.py::_keep_base`, `tools/fabric/secretstore/trust.py::replace_orphaned`*

*Observed 2026-10-18 (python-dev)*

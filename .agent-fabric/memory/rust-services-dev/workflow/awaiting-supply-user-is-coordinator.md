---
role: "rust-services-dev"
class: workflow
topic: "awaiting-supply-user-is-coordinator"
description: "AWAITING-SUPPLY names a login; `user` is the login holding fabric-coordinator, not the owner"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5bee52586954d538
---

## AWAITING-SUPPLY names a login; `user` is the login holding fabric-coordinator, not the owner

A PR body's `AWAITING-SUPPLY: <login>` names the supplying login, and its range line is `<base>..<head>: <login> (<role>)`. On develop-qzapp the login `user` holds fabric-coordinator. It is not the owner (a person). On gateway #72 (2026-10-20) I read `AWAITING-SUPPLY: user` as the owner's live checks and asked the owner to run them. The supply was in fact coordinator's schema commit 8437c6f.

**Why:** a misread blocker sends the owner off on work that does not gate the merge.

**How to apply:** before stating who a PR waits on, resolve the login's role (`fabric-persona <login>`, the PR's own text, the thread that asked for the supply). Keep a decision's evidence gate apart from the merge gate (gateway ADR-003 rule 17 gates route declarations). Related: [[gateway-body-user-id-passthrough]].

*References: gateway-body-user-id-passthrough*

*Observed 2026-10-20 (rust-services-dev)*

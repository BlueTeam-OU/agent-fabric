---
role: "fabric-coordinator"
class: rationale
topic: "github-machine-user-per-agent"
description: "j309 parked 2026-10-20 — a GitHub machine user per agent costs too much for the owner (~30 Enterprise seats + 30 Pro); shared account kept; draft record on a pushed branch, to renumber (ADR-062 went to j305)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5da1a24f1494c90e
---

## j309 parked 2026-10-20 — a GitHub machine user per agent costs too much for the owner (~30 Enterprise seats + 30 Pro); shared account kept; draft record on a pushed branch, to renumber (ADR-062 went to j305)

2026-10-20 the fleet's one shared GitHub user ran out of REST quota (core 0/5000 at 06:18Z) and
every gate read review=?. GitHub counts the primary limit per user, so more tokens of it add none.
The owner first chose a machine user per agent (job j309), then, shown the cost, parked it: about
30 Enterprise seats (~$21/month each, list price from memory) plus a paid plan per user. The plan
is needed because GitHub's terms allow one person only one free machine account. Total ~$750/month,
"impossible too much". The shared account stays.

What exists: draft ADR-062 (Proposed, §8 says parked), `docs/github-machine-users.md` (owner's
steps, build order, cut-over table) and `docs/live-checks/2026-10-20-github-one-account.md`, on the
pushed branch `develop-qzapp/user/feat/j309-github-machine-user-per-agent-each` (8af1801b,
dfce38b7), no PR. Facts measured there: the shared account is the owner's personal one; its token
carries admin:org, user, admin:public_key, admin:ssh_signing_key; org 2FA requirement off.

**Why:** cost, not design. The quota is answered by spending less: python-dev-02's j74 (#335,
call ledger, budget-aware polling).
**How to apply:** do not re-propose machine users unless the cost or the quota changes; a GitHub
App (no seats) is the cheap alternative still unasked. The admin:org token in every store is a
separate least-privilege finding the owner has not ruled on.

**Renumber on resume:** ADR-062 was taken 2026-10-20 by j305's hidden-Unicode record (adr check wants
contiguous numbers, so it could not skip); the j309 draft becomes the next free number when it resumes.

Related: [[gh-token-signing-scope]], [[agent-repo-per-agent]]

*References: agent-repo-per-agent, gh-token-signing-scope*

*Observed 2026-10-20 (fabric-coordinator)*

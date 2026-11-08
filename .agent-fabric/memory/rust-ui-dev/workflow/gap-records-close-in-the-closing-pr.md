---
role: "rust-ui-dev"
class: workflow
topic: "gap-records-close-in-the-closing-pr"
description: "Before asking to arm a PR that closes a recorded gap, grep the gap's own wording across design docs, SECURITY-MATRIX and plan carries; every record it makes false closes in that PR"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5b587c7c110341a8
---

## Before asking to arm a PR that closes a recorded gap, grep the gap's own wording across design docs, SECURITY-MATRIX and plan carries; every record it makes false closes in that PR

A PR that closes a gap someone recorded as owed must also amend every record still describing that gap as open, and in the same PR. InterWeave CLAUDE.md §2 says this only for ADRs and contracts. The arming authority (architect-cto) applies it to every record: "a doc the PR's code contradicts lands in the PR, not after it", and "a record the PR makes false closes in the PR". It holds the arming word until those records are amended.

**Why:** #522 (the names.rs keys, store v12) was ready to arm at a clean head, but it cost two more supply commits and two re-review rounds. The first missed record was the human-client-ui.md §13 sentence. Then the review's F5 found the stale "case key alone" wording in tests/SECURITY-MATRIX.md (TM-56's owed and residual cells) and in the plan's Stage 21 carry, which named my login as owing the gap.

**How to apply:** before the arming request, `git grep` the gap's distinctive phrasing and the owed or carry entries that name you. Look in the design docs, tests/SECURITY-MATRIX.md (the owed, residual and limit cells), and BOTTOM-UP-IMPLEMENTATION-PLAN carries. Amend each one in the PR. A dated close record gets a closing note, not a rewrite. When an owed test becomes real, the matrix cell names the test (check_security_matrix.py verifies the names). Records in another lane's file are that lane's supply commit, so name them in the request instead of leaving them for review to find. Related: [[brief-facts-checked-first]].

*References: brief-facts-checked-first*

*Anchors: `interweave:CLAUDE.md::update the relevant ADR/contract in the same change`, `interweave:tests/SECURITY-MATRIX.md::TM-56`, `interweave:tools/checks/check_security_matrix.py`*

*Observed 2026-10-31 (rust-ui-dev)*

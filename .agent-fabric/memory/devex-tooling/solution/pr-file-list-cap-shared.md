---
role: "devex-tooling"
class: solution
topic: "pr-file-list-cap-shared"
description: "Read a PR's files and commits through evidence.PrEvidence; the caps are common.PR_FILE_LIST_CAP and PR_COMMIT_LIST_CAP, and a list at its cap is Incomplete"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 16889eb5a647950d
  - 8f21e1ef3e89bfe1
---

## Read a PR's files and commits through evidence.PrEvidence; the caps are common.PR_FILE_LIST_CAP and PR_COMMIT_LIST_CAP, and a list at its cap is Incomplete

GitHub lists at most 3000 of a pull request's files and 250 of its commits,
paginated or not, with no error; a gate judged on a capped list judges only
part of the change (external review F08, j282: 3000 docs paths armed docs-only).

Since agent-fabric #513 (W1-B, ADR-067; on main 2026-11-09) both caps live
once, `common.PR_FILE_LIST_CAP = 3000` and `common.PR_COMMIT_LIST_CAP = 250`,
and every reader in tools/fabric/github/ (arm, post_review, pr_counts,
pr_gate, review_checkpoint) reads through `evidence.PrEvidence`:
`files()` / `commits()` return the list only when it is shorter than its cap,
otherwise an `Incomplete` value; `has_commit(sha)` is False only from a whole
list. Unreadable and incomplete stay distinct, and neither becomes an empty
list. The per-module commit caps (arm PR_COMMITS_CAP, pr_counts
REST_COMMIT_CAP) are gone.

**Why:** a capped list is a part of the change; any gate judged on it judges
only that part.
**How to apply:** a new reader of a PR's files or commits uses
`evidence.PrEvidence` and treats `Incomplete` as a refusal, never as an empty
or whole list; it imports no cap of its own. Test with a list of exactly the
cap, plus the cap minus one as the control.

*Anchors: `tools/fabric/github/evidence.py::class PrEvidence`, `tools/fabric/github/common.py::PR_FILE_LIST_CAP`, `tools/fabric/github/common.py::PR_COMMIT_LIST_CAP`*

*Observed 2026-11-09 (devex-tooling)*

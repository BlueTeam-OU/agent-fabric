---
role: "python-dev"
class: workflow
topic: "j67-fabric-errors-merged"
description: "j67 fabric-errors (PR #313 merged) — traps found building a GitHub-artifact reader: gh cuts headlines, git checkout loses edits, lint without the operator, review rounds"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 505e0dca00c6652e
---

## j67 fabric-errors (PR #313 merged) — traps found building a GitHub-artifact reader: gh cuts headlines, git checkout loses edits, lint without the operator, review rounds

fabric-errors (tools/fabric/errors.py, ADR-061 Proposed) merged as #313 on 2026-10-19 after seven blind-review rounds; the fleet view section is next and is the coordinator's request.

**Traps worth keeping**
- `gh pr view --json commits` cuts `messageHeadline` at ~70 chars and ends it in an ellipsis; the whole subject is only in the REST `pulls/<n>/commits` `commit.message` (results.merged_prs now keeps it as `subject`). Any matcher on a headline (fold merges, classifier) must use it. Test fixtures must carry the cut shape.
- A mutation script that restores with `git checkout <file>` throws away uncommitted work in that file: restore from a copy, or commit first.
- Lint without the operator (tests/test_roots_readers.py, test_project_import.py) fails on `$`-ended `re.match` patterns and on "agent-fabric ADR-N" for an ADR not on main; plain `tools/fabric/lint.py` in a checkout with the operator passes. Run the full tests/run.sh with CI's env before the first push. Instance data (hosts registry) goes through `roots.*` and tests inject a fixture.
- The commit hook can fail once on OpenTimestamps ("need at least 2 attestations"); the same commit succeeds when retried, and `&&`-chained pushes then silently do not run.
- A re-review brief may be hand-written compactly (the dispatch header from `fabric-review next` + range + previous findings by label) instead of pasting the 40 KB derived brief; `fabric-review next` still creates the pinned head worktree. Use the request's `card_base` and a pinned range sha, not `HEAD`.
- A reviewer found a bug in each of my fixes' direction (F4 "none" parsing overcorrected, then regressed again): when a fix changes what a parser accepts, enumerate old vs new on real review bodies before pushing.

**Why:** the period/window arithmetic (--days 7 vs --window 14) left the revert/fix denominator empty until the closed period was separated; and a rate over a numerator outside its denominator needs the denominator to be "PRs the row had a commit in".

**How to apply:** for the fleet-view section, reuse `errors.report()`/`tally()`; ADR-061 §5 rule 6 forbids ranking and any verified-work number beside the counts.

*Anchors: `tools/fabric/errors.py::FOLD`, `tools/fabric/results.py::merged_prs`*

*Observed 2026-10-19 (python-dev)*

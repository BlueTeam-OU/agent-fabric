---
role: "python-dev"
class: workflow
topic: "pr-arming-and-ci-traps"
description: "Arming a security-boundary PR under 8 work commits, the ruff gap, a wait-merged flake, and not deleting a worktree under a running suite"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c7f571b3543f1719
---

## Arming a security-boundary PR under 8 work commits, the ruff gap, a wait-merged flake, and not deleting a worktree under a running suite

(1) `fabric-pr arm` on a security-boundary change with under 8 work commits refuses unless the `--basis` text contains the phrase "owner's word" — quote the owner's actual words from the session in it. (2) `ruff` is not installed on the host; `tests/static.sh` skips it locally and CI's `static` and both `platform-smoke` legs fail on an unused import. Before pushing Python, check imports with a short `ast` script over the files `git diff --name-only origin/main...HEAD -- '*.py'` lists; `lint.py` does not run ruff. (3) `fabric-pr wait-merged` gave up twice on "could not read #N checks" while checks were pending (wait_merged.py, not diagnosed); watch the PR with a `gh pr view --json state` loop under Monitor instead. (4) Never `git worktree remove` or delete a log while a backgrounded `tests/run.sh` still runs there — its exit 1 then means nothing; look for the process by pid before cleaning, and a `pgrep -f` / `pkill -f` on a login name is blocked by a hook because it matches the session itself. (5) Post a review of the head BEFORE pushing the fix that answers it, then re-review only the fix range; `fabric-review brief`'s `previous_findings` must be a FILE path (the posted review body saved in the scratchpad), and the range must use the merge-base commit, not `origin/main..HEAD` once main has moved. (6) `workingcopy.py` is outside python-dev's entry: the hook refuses the commit and stages it with `git add -A` first, so `git restore --staged --worktree` it before recommitting.

**Why:** each cost a round trip in the #126 session.
**How to apply:** before arming, pushing Python, or cleaning a worktree.

*Observed 2026-10-09 (python-dev)*

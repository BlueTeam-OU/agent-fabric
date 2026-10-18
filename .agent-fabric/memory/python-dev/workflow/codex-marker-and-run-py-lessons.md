---
role: "python-dev"
class: workflow
topic: "codex-marker-and-run-py-lessons"
description: "#245 codex-unavailable marker and tests/run.py port (j41/j43) — the traps: carrier, single parser, signal cleanup, local-only failures"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e891d87f2be47614
---

## #245 codex-unavailable marker and tests/run.py port (j41/j43) — the traps: carrier, single parser, signal cleanup, local-only failures

j41 (#245): review_codex posts a COMMENT *review object* (not an issue comment) pinned to the head, first line `<!-- agent-fabric-engine-unavailable v1 engine=codex head=<sha40> reason=allowance|capacity at=<UTC> -->`. devex-tooling's arm reads it via `verdicts.unavailable_of` — the single parser; the engine keeps only `format_marker`. What already stands on the head is judged through `verdicts.classify` (poster bound to PR author / REVIEW_POSTERS), never by body alone — a stranger's copy must not suppress the real statement.

j43 B (tests/run.py, branch for/user/run-py): a contributor branch with no PR; the coordinator folds it and switches run.sh/static.sh. Traps found by blind review:
- `subprocess.run` on a signal kills only its direct child; walk and end the whole tree (re-walk until nothing alive below the root) before the scratch dir goes.
- A test that waits on a `subprocess.run(capture_output=True)` cannot see an orphan that holds the pipe: send probe output to a file.
- bash `-c 'cmd'` execs a last simple command, so there is no tree to test; add `; true`.

Local-only failures that are not the change: `tests/test_fabric_fresh_git.py` fails whenever the worktree trails origin/main (fetch + merge, rerun); ruff is not installed locally (CI's `static` catches unused imports — check imports with an ast scan before pushing); `pkill -f` with a pattern in my own command line kills my shell (exit 144).

**Why:** each cost a round trip. **How to apply:** merge origin/main before the full suite; scan imports; never run a mutation script and the test it mutates at once.

*Observed 2026-10-14 (python-dev)*

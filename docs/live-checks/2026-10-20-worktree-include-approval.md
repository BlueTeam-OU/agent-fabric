# 2026-10-20 — a linked worktree reads its main checkout's import approval

Run by fabric-coordinator, as the login user, on Claude Code 2.1.286 (job j174, from the review of #233). The question: `workspace_trust.py` writes `hasClaudeMdExternalIncludesApproved` under each folder's own realpath, and a fleet session often starts in a linked worktree (`agent-fabric-j174-…`, a subagent's worktree). Which entry of `~/.claude.json` does Claude Code read there — the worktree's own, or its main checkout's?

## What was measured

Rebuilt in the scratchpad, as on 2026-10-13 (`2026-10-13-agents-md-import.md`): a `projects/` holding the workspace template (`runtime/claude-code/workspace/CLAUDE.md`, which imports `@agent-fabric/CLAUDE.md`), `agent-fabric` a link to the fabric's checkout, a git repository `someproj` with one commit, and `someproj-wt` a linked worktree of it (`git worktree add`), beside it.

Each run set the three keys `workspace_trust.py` writes on the folders named below, `hasTrustDialogAccepted` alone on the other, then ran `claude -p --output-format stream-json --verbose` in `someproj-wt` with every tool disallowed, and took the first assistant message (the Stop hook's later turn ignored). The prompt asked for the first line under "The invariant" (from `AGENTS.md`, reached only through the import) and the instruction files received. The scratch entries were removed from `~/.claude.json` after each run.

| approval on | the invariant line | files received |
|---|---|---|
| neither | absent | `projects/CLAUDE.md` |
| `someproj` (main checkout) only | quoted | `projects/CLAUDE.md`, `agent-fabric/CLAUDE.md`, `AGENTS.md` |
| `someproj-wt` (the worktree) only | absent | `projects/CLAUDE.md` |
| both | quoted | all three |

Claude Code wrote nothing under either entry during the runs.

## What it decides

In a linked worktree `claude -p` reads the external-include approval of the **main checkout**, never the worktree's own path. Only sibling directories without links were tested, so how Claude Code finds the main checkout (the common git directory, or otherwise) is not shown. So, for this key:

- A worktree of a checkout bootstrap approved loads the fabric's rules with no approval of its own: `workspace_trust.py` need not write the approval for worktrees. Whether the trust key needs a worktree entry is not shown (below).
- The entries for worktree paths in an account's `.claude.json` are inert for this key. They do no harm and need no sweep.
- A checkout with no approval (absent; `false` was not run) disables the fabric's rules in **every** worktree of it, even with the worktree's own approval set (the one value run). The fix is the checkout's entry (bootstrap's `trust` step for registered copies), never a worktree's.

## Not verified

- `hasTrustDialogAccepted`: set on both folders in every run, so which entry the trust question reads in a worktree was not measured (`claude -p` does not ask it).
- An interactive session (the approval dialog, and whether its answer is written under the main checkout's path).
- A worktree whose main checkout is at an unrelated or symlinked path, which would show how the main checkout is found.
- A worktree outside `projects/`: it would not find the workspace `CLAUDE.md` among its parents at all, approval or not.

---
name: branch-hygiene
description: "Local branch hygiene in a working copy: list every local branch and worktree against the remote's freshly fetched default branch, delete on your own what is wholly on it, and bring the rest to the person with its commits and pull request. Load it when the session-start context says \"branch sweep due\", when asked to clean up branches or worktrees, or before deleting any local branch."
---

# Local branch hygiene

Branches and worktrees pile up: one per pull request, one per subagent
worktree, local copies of other agents' branches fetched to review them.
The sweep removes what is provably merged and puts the rest in front of
the person. `fabric-branches` does the counting and the deleting; this is
when to run it and what to do with what it reports.

## 1. Orient

Run it only when nothing is using the tree: no subagent dispatched on
this working copy still running, no background job reading it (a suite, a
build). If one is, wait for it. Do not switch branches for the sweep;
`fabric-branches --sweep` refuses a working copy with uncommitted
changes, and never touches the branch you are on or the default branch.

## 2. Report, then sweep

```sh
fabric-branches            # the table; deletes nothing
fabric-branches --sweep    # the same table, then the deletion
```

Both fetch `origin` first with a plain `git fetch origin`. A refspec fetch
does not move the remote-tracking refs, and a stale one makes merged work
look unmerged. If the fetch fails, the command stops. Do not count by
hand against the old ref.

What they count against is the remote's default branch: `origin/HEAD`,
else the `default_branch` the project registry gives this working copy.
A project's default can be `master`, so it is never guessed as `main`.
When neither says, the command stops with exit 2 ("the default branch of
origin is unknown") and counts nothing. `git remote set-head origin
--auto` sets `origin/HEAD` from the remote; a clone of an empty
repository, or an older git that does not set it on fetch, is the usual
cause.

The number beside each branch and worktree is how many of its commits
are **not** on the default branch:

- **0**: everything on it is on the default branch. `--sweep` deletes it, re-counting
  at deletion. A worktree at 0 is removed only when it has no changes
  (untracked files included), no ignored files (a `.env`, a build that
  removal would delete) and no lock, and is not the one you run in; the
  others are listed with the reason they stay. You do this without
  asking; losing nothing is provable.
- **More than 0**: kept, and listed with its commits and its pull
  request. This is either work you still owe or a decision for the
  person. Never delete it in a sweep.
- **Tracks another agent's branch**: a local copy only. Deleting it at 0
  is fine. Never delete their remote branch, and never push to it.

A branch whose pull request shows `MERGED` but still counts more than 0
was squashed, or its history was rewritten. The count cannot prove it is
merged; the person can.

## 3. Bring the rest to the person

After a sweep, tell the person three things:

- what was deleted, by name and SHA (the command prints both);
- each kept branch with its commits and its pull request state, and what
  you propose: finish it, open its PR, or ask them to let it go;
- `git branch` as it now stands.

Delete a kept branch only on their word, one branch at a time, with
`git branch -D <branch>`.

## Never

- `git push --delete`, or any other remote cleanup: the merge queue owns
  remote branches.
- A deletion based on a count taken before the fetch.
- A sweep with a subagent or a background job still working on the tree.

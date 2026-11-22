# `fabric-ctl all upgrade fabric`, first run (2026-09-26)

Run by develop-qzapp/user right after #47 merged (0ec9159) and was
distributed by hand one last time (every daemon predated the `fabric`
piece). 16 accounts, 9.5 s wall-clock.

- 15 rows `current 0ec9159 (main)`: each account fetched, found itself at
  the commit, and ran its bootstrap anyway — the launcher pulls but never
  bootstraps, so "current" is not "installed".
- No session stopped: every running one reads `running: next launch uses
  it`; three accounts had none.
- 1 row `refused`: language-culture-ge's checkout was on
  `develop-qzapp/language-culture-ge/locale/ge-header-bare-commands`
  (merged as #44). Nothing moved; the account was asked to switch to main
  (relay seq 6272).
- Exit 1, because of the refusal — a fleet run that is not all green says so.

## What the refusal showed about the old way

The manual distribution minutes earlier ran `git pull --ff-only origin
main` in the same checkout and reported rc=0: on a branch, that command
fast-forwards the checked-out BRANCH to main. It was harmless here (the
branch was merged), and invisible. The command refuses the same checkout
by name — which is the difference between distributing and quietly
moving someone's branch. The hostexec loop is kept only for a daemon that
predates a change to `upgrade` itself.

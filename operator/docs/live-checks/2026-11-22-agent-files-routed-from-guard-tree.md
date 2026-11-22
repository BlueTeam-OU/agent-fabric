# Agent files routed from the guard's tree, read back on a host — 2026-11-22

*Host develop-qzapp, account `user` (fabric-coordinator), job j810, PR #688 at
4a78d96b. Managed settings are in force here, from snapshot
`fabric-ca82ece06fceb3ca3fd42e21aaf8de62607d7c61`, which `fabric-status` reports
as drifted from origin/main (151 paths). The claim covers this build of the
installer and status against that installed snapshot on this date.*

## What was measured

The branch's `install_agent_files.py` and `status.py` were run from the job's
worktree (`AGENT_FABRIC_ROOT` set to it) against the real
`/etc/claude-code/managed-settings.json`. Nothing was written.

- `dispatch_guard_tree()` returned
  `/usr/local/lib/agent-fabric/managed/fabric-ca82ece0…`. That is the snapshot
  the `current` link names, the same tree `hook_entry.py` gives the dispatch
  guard.
- `routing_run("pins"|"efforts", "anthropic", <worktree>, <snapshot>)` ran the
  snapshot's own `routing.py` with `-E -s --fabric <snapshot>`, under the
  environment the snapshot's `hook_entry.py` builds. Both calls exited 0.
  - pins: `code-review fable claude-opus-5-5`
  - efforts: code-low, code-medium and code-high `medium`; code-plan and
    code-review `high`.
- The account's agent files, written at this session's launch: code-review.md
  has `model: claude-opus-5-5` and `effort: high`; code-plan.md has
  `effort: high`; the other three classes have `effort: medium`.
- `agent_file_routing_drift(<worktree>, "anthropic")` returned no lines. The
  checkout and the snapshot route every class alike today, and every file
  agrees with the snapshot.

## What it decides

- The snapshot behind main accepts the installer's new call: `--fabric`, and
  the environment taken from its own `hook_entry.py`. On a drifted host the
  call works, rather than failing into the installer's "routing.py pins
  failed" exit.
- The files this account runs with are what the guard compares to, so this
  session's dispatches pass the check that denied every review from
  2026-11-12 until the reinstall.

## What it does not show

No routing change separated the checkout from the snapshot on this date, so
neither window of ADR-043 §5 rule 10 was exercised live: a merge before the
reinstall, or running sessions after it. Both are covered by
`tests/test_fabric_status.py` and `tests/test_install_agent_files.py`. The
first routing merge after #688 lands is the live case; read
`fabric-status` before and after that reinstall.

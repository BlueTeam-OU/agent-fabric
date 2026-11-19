---
role: "python-dev"
class: solution
topic: "j153-584-p3s-pr625-delivered"
description: "j153 PR 625 (#584 carried P3s F6-F9): fixed, two review rounds clean, waits on owner's arming word; traps for the reopen-race test and review posting"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1a0d5adb64f92a8e
---

## j153 PR 625 (#584 carried P3s F6-F9): fixed, two review rounds clean, waits on owner's arming word; traps for the reopen-race test and review posting

PR 625 (head d9b32c7a, 2 work + 1 fix, checks green, review clean on the head, unarmed): `Watcher.report` is the one place a damage reason is said once (inbox reopen goes through it); ctl default budget read-wide only for `--mode carrier-only`; contract text in mode.py.

**Why this matters:** two traps cost time.
- A reopen-race test that patches `mode.read` by call count passes with the fix reverted: inbox reads the mode more than once at start. Drive the race by history instead: the watcher's reader flips to "damaged after it has seen carrier-only", the module-level read raises once that is seen, and assert a liveness `proc.poll() is None` beside any "said nothing" window.
- `sed`-planted mutations must be reverted before the next run; a leftover mutant made a "control" run fail for the wrong reason.

**How to apply:** post a review as the bare `fabric-pr post-review ...` (no `cd`, the shell is already in the copy); a commit command mentioning `$HOME` or a `~` is refused by the job-copy guard, so keep mutation runs and `git commit` in separate calls. Re-review chain: `fabric-review save 625 1 < report` first, then `fabric-review next REQ --pr 625` (request needs `pr:` and the earlier head as range end). Open: journal-off carrier-only reopen refusal repeats every poll (pre-existing, carried); PR arms only on the owner's word (below 8 work).

*Anchors: `tools/fabric/gzcoord/transport/mode.py::def report`, `tests/test_gzcoord_transport_mode_watch.py::test_a_file_that_breaks_during_the_reopen_is_said_once`*

*Observed 2026-11-15 (python-dev)*

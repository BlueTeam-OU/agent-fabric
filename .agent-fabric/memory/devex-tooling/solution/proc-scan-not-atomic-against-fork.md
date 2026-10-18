---
role: "devex-tooling"
class: solution
topic: "proc-scan-not-atomic-against-fork"
description: "killing a check's leftovers by a /proc scan (by session or cwd) misses a child forked mid-scan; rescan until no one new — trial-merge lease flake j128"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7153fecedd6eb2fd
---

## killing a check's leftovers by a /proc scan (by session or cwd) misses a child forked mid-scan; rescan until no one new — trial-merge lease flake j128

A single /proc pass that SIGTERMs every process of a session is not atomic
against fork, unlike killpg: a member signalled just after it forked leaves
a child the listing never had. On this host /bin/sh is bash 5.3, so
`sh -c 'cd / && sleep N & exit 0'` is a subshell that forks its sleep —
exactly that window. trial-merge's cleanup (tools/fabric/github/trial_worktree.py)
reaches a lease-run check only by session (fabric-lease's set -m moves it
out of the group), so under a full tests/run.sh's load the sleep outlived
the run: test_trial_merge_cli's "what it left running in its own group
under the lease is ended too" failed, alone passed.

Measured 2026-10-14 with 20 CPU hogs: old single pass 4/60 and 3/150
survivors, rescan-until-nothing-new 0/150. The fix rescans until a pass
finds no un-signalled member (a process with a fatal signal pending cannot
complete a fork), bounded by SWEEP_PASSES; test_trial_merge.py holds a
scripted-listing case whose one-pass mutant fails.

**How to apply:** any "end everything the child left" by scanning /proc
needs the loop; a flake that only shows under parallel suites and involves
a background `&` in sh is this race first.

*Anchors: `tools/fabric/github/trial_worktree.py::SWEEP_PASSES`, `tests/test_trial_merge.py::scans again until a pass finds no one new`*

*Observed 2026-10-14 (devex-tooling)*

---
role: "python-dev"
class: solution
topic: "new-agent-suite-execs-and-sweep-roots-j73-j74"
description: "j73 #342 (where the new-agent suite's execs were: the login shell's host profile) and j74 #339 (CLAUDE_CODE_TMPDIR scratch roots, a test time bomb); measuring and review traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 44069e3561755afc
---

## j73 #342 (where the new-agent suite's execs were: the login shell's host profile) and j74 #339 (CLAUDE_CODE_TMPDIR scratch roots, a test time bomb); measuring and review traps

**Execs (#342).** `strace -f -qq -e trace=execve -o F python3 tests/<x>.py` with `env -i` and a TMPDIR of its own; count `execve(.*= 0$`. test_new_agent_cli was 29,648 execs, ~25/28 from /etc/profile.d: the worker's `bash -lc` ran 1,386 times under the sudo fake, each sourcing the host's profile. The sudo fake now logs `bash -lc` as built and runs `bash -c`; `has_line` (bash) replaces `grep -qsxF` in the fakes: 15,097 execs. A plain-shell fake loses what a real login shell caught (Debian's /etc/profile assigns PATH outright): the worker's and verify's `export PATH=` re-assertions each have a real-login-shell case, mutation-tested (the review found the worker's was unguarded after the change).

**Sweep roots (#339).** The harness keeps scratch under `$CLAUDE_CODE_TMPDIR/claude-<uid>/<project>/<session>` when set, else TMPDIR: `claude_tmp_roots()` sweeps both; a link root is not "seen". Any suite that sweeps with a readable empty registry reads every scratch dir under both roots as ended: it must own TMPDIR and CLAUDE_CODE_TMPDIR (my first run deleted this login's real scratch, task outputs included); a guard in test_branches_sweep fails one that inherits.

**Why (traps):** (1) a test that calls `collect()` with the real clock against fixed-date fixture rows is a time bomb: test_control_ops' ledger case went red for every CI run at 2026-10-20 12:00 UTC; the fix window needs a margin between the counted rows and the excluded row (my first margin sat on it: the review froze the clock to show it). (2) `fabric-review next` needs a request whose range is the first round's pinned shas; a diff-file request reviews the working tree with no head, so `fabric-pr post-review --head <full sha>` and never an invented header. (3) A requirement that names what was fixed refuses to render: state what must be true. (4) Load average 45-90 on this host makes gzcoord and `took < 1.5 s` cases fail in a full run and pass alone; read the summary of failed suites, and run each alone.
**How to apply:** before cutting a suite's cost, count execs by program first; after cutting a real shell out of a fake, name where its evidence moved.

*Anchors: `tests/test_new_agent_cli.py`, `tools/fabric/branches.py::claude_tmp_roots`, `tests/test_provisioning_worker.py`*

*Observed 2026-10-20 (python-dev)*

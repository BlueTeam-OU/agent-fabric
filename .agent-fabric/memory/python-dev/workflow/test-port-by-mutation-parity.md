---
role: "python-dev"
class: workflow
topic: "test-port-by-mutation-parity"
description: Porting a bash TEST to Python has no oracle of its own — prove it by planting mutations in the implementation that both suites must fail; how to run that without losing hours
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 455fcf1208bd072f
---

## Porting a bash TEST to Python has no oracle of its own — prove it by planting mutations in the implementation that both suites must fail; how to run that without losing hours

Wave 6 of ADR-040 (j4, 2026-10-02, branch develop-qzapp/python-dev-01/for/user/wave-6-tests)
ported the bash tests themselves. A port of a test cannot be checked against the old test's
output, so the evidence is mutation parity: for each behaviour the bash test asserts, plant one
small mutation in the IMPLEMENTATION; the bash test and the Python port must BOTH fail, and both
pass on the unmutated tree.

What a mutation result means:
- both fail: parity for that behaviour.
- only bash fails: a gap in the port — fix the port (store-enroll: its two homes were created in
  one millisecond, so a child's birth read on the parent looked identical).
- only Python fails: the port is stronger — say why (launch: bash counted `--effort` lines with
  `grep -c`, the port counts occurrences; see [[oracle-blind-spots-in-ports]]).
- neither fails: first suspect the plant — a second guard in the code absorbed it, or the edit
  did not apply. Re-plant to defeat the second guard; only when the behaviour truly cannot change
  under that fixture is it a shared blind spot, reported as such, parity intact.

How to run it (lessons that cost hours):
- A scratch runner (never committed): apply one edit set, run both suites under CI's environment
  with their own TMPDIR, restore the file, print one line per mutation WITH flush — a killed run
  otherwise loses everything it measured.
- Background Bash runs are killed at 30 min unless `timeout` is raised (max 2 h): chunk long sets
  (the launcher: ~6 min a mutation) with a skip/limit.
- Run independent sets in parallel in scratch `git worktree add --detach` copies, uncommitted
  test files copied in; never two sets mutating the same tree.
- Run each bash test the way tests/run.sh runs it: some go through policies/run_suite.sh, some
  (test_qubes-accounts.sh, which removes `install` from PATH on purpose) with plain bash, or the
  bash baseline fails.
- A hung oracle (a mutation that stops a signal) must be killed by session, not pattern; holders a
  test starts should lead their own session so cleanup reaches the groups they spawn.

**Commit before planting (2026-10-04, arm-waiver follow-ups).** A mutation loop that restores the
file with `git checkout <file>` restores it to HEAD: uncommitted fixes in that file are gone,
silently — the suite then fails on the missing fix, which reads like a broken mutation. Commit the
change first (the brief says mutations run "after the fix is committed" for this reason), or restore
from a saved copy of the file, never from git.

*References: oracle-blind-spots-in-ports*

*Observed 2026-10-02 (python-dev)*

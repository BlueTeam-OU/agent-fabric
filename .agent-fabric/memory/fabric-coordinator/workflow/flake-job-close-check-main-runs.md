---
role: "fabric-coordinator"
class: workflow
topic: "flake-job-close-check-main-runs"
description: "closing a flake job whose fix another holder merged — list main's CI runs since the merge and grep each red one for the flake's own signature before done"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8c63791ec308af3a
---

## closing a flake job whose fix another holder merged — list main's CI runs since the merge and grep each red one for the flake's own signature before done

A flake job blocked on a holder's job (j799 on python-dev-01/j230) clears when
their PR merges (BlueTeam-OU/agent-fabric#574, 2026-11-12). Before `fabric-jobs done`:
`gh run list --branch main` since the merge, then `gh run view <id> --log-failed`
on each red run, grepping for the flake's signature (here `tokens.days`/KeyError).
On 2026-11-13 three red main runs were other suites (test_reads_live, a carrier
socket BrokenPipe, stripped-nightly), not the closed flake. Each one became its own
job (j850), not a reason to reopen. Related: [[deferred-finding-job-closed-by-another-pr]].

*References: deferred-finding-job-closed-by-another-pr*

*Anchors: `tests/test_control_agentd.py::tokens`*

*Observed 2026-11-13 (fabric-coordinator)*

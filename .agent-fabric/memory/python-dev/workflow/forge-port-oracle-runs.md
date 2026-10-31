---
role: "python-dev"
class: workflow
topic: "forge-port-oracle-runs"
description: "How to run a managed project's bash test as the oracle for a forge-script port into agent-fabric, with no clone of that project on this login"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3920ce3e764aa65b
  - a7e2303ad8dd8111
---

## How to run a managed project's bash test as the oracle for a forge-script port into agent-fabric, with no clone of that project on this login

No gzapp working copy exists on python-dev-02; the oracle is fetched at the
contract's commit with `gh api "repos/gzapi-org/gzapp/contents/tools/gh/<f>?ref=<sha>" -H 'Accept: application/vnd.github.raw'`
into the scratchpad, beside the bash original and whatever it sources
(wait-merged needed actions-health.sh and fabric-root.sh).

Method used for wait-merged (commit defd2132, 2026-10-08):
1. pristine test against the bash original — baseline (219 ✓, ~50 s fast clock);
2. teach the test's gh mock gh.py's transport (ADR-040 §5 rule 5): answer
   whole JSON when the call carries no `-q/--jq`; re-run the bash original
   against the extended mock — must stay green;
3. a scratch `tools/gh/<name>.sh` forwarder beside the test (the test finds
   UNDER_TEST as `$SCRIPT_DIR/<name>.sh`) that maps the project's env names
   to the fabric's, sets GH_REPO, AGENT_FABRIC_ARM_CONFIG and any test seam,
   then execs `<worktree>/runtime/github/<name>.sh`;
4. the oracle is not committed; its counts go in the commit message.

A fast clock through BASH_ENV does not reach Python: devex-tooling ruled
(seq 20831) the oracle runs on the real clock (~244 s for wait-merged) and
the Python test patches its own clock in process. Plant oracle mutations
too: the wait-merged oracle never pinned the checks-failure reset — a
mutation survived it and needed a Python case. See [[forge-port-queue]].

**Oracle cases that cannot cross into Python (seen on pr-compliance, wait-merged, guards-wired):**
a bash test's seams reach only a bash script: a BASH_ENV clock, a stub sourced from
`$AGENT_FABRIC_ROOT/...`, a stub logging what the classifier was told, per-script env
names (CHECKS_DIR, GH_REPO_OWNER). Before coding, list each oracle assertion that tests the
test's own seam, not the script; put the list to the contract's owner with a proposal per case
(retire it and pin the fact by patching in process, or add one named env seam the forwarder sets).
Never add a clock or stub seam to production code unasked. A forwarder that finds the fabric
through AGENT_FABRIC_ROOT breaks when the oracle points that at its sandbox.
**Why:** the oracle runs unchanged is the parity proof; a case that can only fail on the
test's seam proves nothing and blocks the port until ruled.
**How to apply:** run the pristine oracle through the scratch forwarder first; the cases that
fail for seam reasons are the list, the rest must pass unchanged.

*References: forge-port-queue*

*Observed 2026-10-08 (python-dev)*

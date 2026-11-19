---
role: "python-dev"
class: solution
topic: "j231-f4-budget-and-launcher-marker"
description: "#575 F4 fix shape (refresh --budget shares) and the AGENT_FABRIC_PULLED leak into tests and the claude child; guard and suite-lease traps met"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c7a220ddaad5c68b
---

## #575 F4 fix shape (refresh --budget shares) and the AGENT_FABRIC_PULLED leak into tests and the claude child; guard and suite-lease traps met

Operator checkout refresh (`tools/fabric/operator_checkout.py`): `refresh(..., budget)` gives the operator fetch 30 % and the engine fetch 50 % of the caller's bound; moveto passes `--budget 30`. A hung remote is simulated with `remote.origin.uploadpack` pointing at `exec sleep N`; the pipe holder outlives the kill, so keep N short, and a mutant needs N above the caller's bound to fail (heads ac66f3e1, 44fd6e6c, f406e51c on for/user/j766-operator-checkout).

A session launched after a pull carries `AGENT_FABRIC_PULLED=1`; tests calling `keep_fabric_current` must clear it (and ALLOW_STALE) themselves. The launcher now pops it before `run_session`; fake claude in `tests/test_launch_cli.py` prints it.

**Why:** coordinator's run was red where mine and CI were green.
**How to apply:** run launcher-touching tests with the marker exported once.

Traps: the job guard refuses `git commit`/`push` chained with other commands or with `$VAR` paths — one literal call each. `tests/run.sh` waits on the host-wide full-suite lease (another account held it for hours). The launcher's `die()` text is in the exception, not stderr. See [[post-review-pins-the-head-it-sees]].

*References: post-review-pins-the-head-it-sees*

*Observed 2026-11-12 (python-dev)*

---
role: "python-dev"
class: workflow
topic: "j68-hooks-port-merged"
description: "#318 merged: statusline/tab_title/plan_hold modules; -I sys.path, forwarder exit 0 without the pin, reviewer traps, brief shortcuts"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ce77c0b6029a7ffc
---

## #318 merged: statusline/tab_title/plan_hold modules; -I sys.path, forwarder exit 0 without the pin, reviewer traps, brief shortcuts

BlueTeam-OU/agent-fabric#318 merged (10 work, 4 fix, 1 merge): tools/fabric/{statusline,tab_title,plan_hold,hook_common}.py; the coordinator made the three .sh forwarders and deleted test_statusline.sh / test_plan-hold.sh.

**Why it matters:** traps found, each by review or the coordinator, none by my first run.
- A module run by a forwarder is `python -I`: its own directory is off sys.path, so a sibling import (`import git`) needs `sys.path.insert(0, HERE)`; an oracle case must run the module with -I (tests/hook_harness.run_isolated).
- `env -i ... VAR=x` in a loop wiped my override variable: the "module" runs were the bash. Check the override reached the oracle (print which entry ran).
- A hook keeps the old script's contract: exit 0 even without the pin (coordinator decision 536443f5), so a forwarder case runs with AGENT_FABRIC_PYTHON naming no file.
- An oracle case that depended on the bash's tool (jq) must become one that fails for both implementations, and its docstring's mutation list must still be true; a reviewer ran the base oracle against a mutated copy of the old bash to prove it.
- A new test of "nothing written" must look where a mutant would write (the fallback under HOME), not where it was already impossible.

**How to apply:** for a hook port, run the oracle through the forwarder and the module, plant mutations on the committed source, and for a re-review brief over 64 KB of diff dispatch with the diff replaced by a `git diff` command in the head worktree; a coordinator-owned conflict (tests/run.py) goes to the coordinator with the exact resolution, and a pushed merge disarms the PR: re-review the merge range, re-arm on the same owner's word.

*Observed 2026-10-19 (python-dev)*

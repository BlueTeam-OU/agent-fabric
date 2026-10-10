---
role: "python-dev"
class: workflow
topic: "static-skips-ruff-here"
description: "before delivering Python to agent-fabric — ruff is not installed on python-dev-01, tests/static.sh skips it and still says \"ruff clean\""
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8027661b8c60358c
---

## before delivering Python to agent-fabric — ruff is not installed on python-dev-01, tests/static.sh skips it and still says "ruff clean"

On python-dev-01 there is no ruff; tests/static.sh prints "! ruff not
installed: not run here (CI runs it)" and then "static: ... shellcheck and
ruff clean", exit 0. j49's e66092d0 shipped two unused imports (F401) that CI
caught in the coordinator's run (REQUEST 01a11625, fix 6fc6ce07).
**Why:** a skip reads as a pass in the summary line; my green run.sh was not
CI's.
**How to apply:** before every delivery, run ruff myself:
`python3 -m venv $SCRATCH/ruffenv && $SCRATCH/ruffenv/bin/pip install ruff`
(CI installs it unpinned; match the version the coordinator reports), then
`ruff check --no-cache .` in the worktree, and remove the venv. Read static's
"!" lines, not only its summary. Related: [[suites-inherit-launch-stamps]],
[[review-before-suite-and-numeric-guards]].

*References: review-before-suite-and-numeric-guards, suites-inherit-launch-stamps*

*Observed 2026-10-07 (python-dev)*

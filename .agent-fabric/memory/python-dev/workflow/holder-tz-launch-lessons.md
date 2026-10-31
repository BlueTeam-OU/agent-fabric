---
role: "python-dev"
class: workflow
topic: "holder-tz-launch-lessons"
description: "j56 — holder timezone exported as TZ; restart inherits the env, so a launcher-set TZ needs a stamp; authority-fenced files go as a patch"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4400a8c4d823e613
---

## j56 — holder timezone exported as TZ; restart inherits the env, so a launcher-set TZ needs a stamp; authority-fenced files go as a patch

A variable the launcher sets that is also a general one (TZ) cannot be popped when unknown (the operator's), yet a restart re-executes with the previous launch's environment: stamp what was set (AGENT_FABRIC_LAUNCH_TZ) and drop TZ only when it still equals the stamp (tools/fabric/launch.py, launcher/holder.py, 2026-10-18). A value that now sets every process's clock (TZ) must be validated (IANA): an unknown name is silent UTC.

**Why:** the blind review of j56 found both; a fixture's invented timezone name broke once validation was added.
**How to apply:** when a request asks for a change in a file outside the authority entry (install_agent_files.py), the commit hook refuses it; stage the rest, deliver the rest as a branch and put the rest as a `git apply` patch in the REPLY body (verified with `git apply --check` and the suite). An empty commit is refused too, so a Supplier-Review trailer goes in the REPLY text then. fabric-review brief needs `card_base` (merge-base with origin/main) when the base is a branch.

j57 follow-up (#294 review): the stamp alone loses the operator's own TZ across a restart — keep it in a second stamp (AGENT_FABRIC_OPERATOR_TZ) and restore it; one function (holder.settle_tz) owns the whole table. A mutation that narrows a condition survives unless a test has the operator change TZ between launches. Launcher is run with `python -I`, so a PYTHONPATH sitecustomize cannot fake "no tz database": edit the copied addenda_check in the fixture tree instead.

*Observed 2026-10-18 (python-dev)*

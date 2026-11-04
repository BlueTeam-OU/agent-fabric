---
role: "python-dev"
class: solution
topic: "j172-start-stop-merged-385"
description: "interweave-start/-stop merged in #385; what a live run found that fakes missed (client program, cold carrier 29 s, restart of a unit that ran)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e028974eed5cfacb
---

## interweave-start/-stop merged in #385; what a live run found that fakes missed (client program, cold carrier 29 s, restart of a unit that ran)

j172 merged as BlueTeam-OU/agent-fabric#385 (2026-10-25, 5 work + 5 fix, boundary change under 8 armed on the coordinator's AUTHORIZES id passed with --authorization). Replaces [[j172-carrier-start-stop-state]].

The live start on a real account found three things the fakes did not: the client unit's ExecStart program (~/.local/libexec/interweave/client, from gzcoord/carrier/install_client.py, not the release) was absent, so start now refuses on it; a cold carrier needs ~29 s (26 roster rows) before `status` answers, so start polls 45 times (STARTUP_STATUS_POLLS), budget 940 s; a unit that already ran keeps the old config.yaml, so start restarts it after the render. systemctl `enable` prints "Created symlink" on stderr: the reason line skips it.

**Why:** a budget test as a lower bound survived removing a term (slack of +20); pin it term by term with assertEqual.
**How to apply:** other accounts need install_client.py (bootstrap) before `interweave-start`; coordinator owns the F6 ADR-029 row text (client-program refusal, check-only and lone-unit paths) and the ctl.py usage line has the same gap (mine, not yet fixed). A gzcoord-compose -o onto an old message file refuses: use a fresh name.

*References: j172-carrier-start-stop-state*

*Anchors: `tools/fabric/control/carrier_install.py::carrier_start`*

*Observed 2026-10-25 (python-dev)*

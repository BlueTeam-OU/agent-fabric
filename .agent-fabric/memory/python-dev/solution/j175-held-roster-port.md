---
role: "python-dev"
class: solution
topic: "j175-held-roster-port"
description: "interweave-start \"activating after 5 looks\" = a daemon crash-looping on EADDRINUSE; old ssh source port holds the roster port; PR #392 state and traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9a87d6ffe8834d78
---

## interweave-start "activating after 5 looks" = a daemon crash-looping on EADDRINUSE; old ssh source port holds the roster port; PR #392 state and traps

language-culture-ru's daemon stayed "activating" because 127.0.0.1:47130 was the source port of a 5-day-old ssh (the deck's) connection, older than ip_local_reserved_ports. Type=exec + Restart=on-failure turns an exit 1 into activating/auto-restart. Found from /proc/net/tcp alone (no journal access across accounts); the coordinator confirmed and ended the ssh.

PR BlueTeam-OU/agent-fabric#392: `unit_diagnosis` (SubState, Result, ExecMainStatus, NRestarts, journal tail) in the channel-check reason; `port_holder_problem` refusal before render.

**Why:** an exemption keyed on `daemon in running` (RUNNING includes "activating") skipped the check in the very incident; review F2. Key on `states[daemon] == "active"`.

**How to apply:** a fake `run` that feeds a sequence to every `show` breaks when a new `show` call is added; match the exact property. A command mixing `$VAR` with `git commit`/`git push` is refused by the job guard (it cannot resolve the directory): commit and push in their own plain commands. Suite reds with ENOSPC: /tmp is a 2 GB tmpfs and my own old `af-t.*` dirs filled it; df first. See [[suite-red-check-df-first]].

*References: suite-red-check-df-first*

*Anchors: `tools/fabric/control/carrier_install.py::port_holder_problem`, `tools/fabric/control/carrier_install.py::unit_diagnosis`*

*Observed 2026-10-26 (python-dev)*

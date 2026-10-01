---
role: "fabric-coordinator"
class: solution
topic: "control-plane-daemon"
description: "Fleet facts in real time come from bin/fabric-ctl (a daemon per account on the relay's fabric:control channel), not from sudo loops; what to know when one account stays silent"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 2b89e2828548489c
  - d0f75075ca6d9001
---

## Fleet facts in real time come from bin/fabric-ctl (a daemon per account on the relay's fabric:control channel), not from sudo loops; what to know when one account stays silent

Since 2026-09-17 every placed account runs `agent-fabric-agentd` as a
systemd user unit (`runtime/control/`, installed by `bootstrap.sh` at
moveto entry); `bin/fabric-ctl all status` asks them all over the relay
and answers in about a second (`agent-fabric ADR-029 (docs/adr/ADR-029-the-control-plane-a-control-agent-per-account.md)`,
`docs/live-checks/2026-09-17-control-plane.md`). `bin/fabric-usage` is
the sudo fallback.

**Why:** the CEO wanted usage, the signed-in Claude account, key
fingerprints and the fabric head per account without the coordinator's
"god mode"; the first table was made by hand, the second only worked as
`user` through sudo.

**How to apply:** a `no answer` row means that account's daemon is down
or on old code — `fabric-host <host> run --as <login> -- bash -lc
'XDG_RUNTIME_DIR=/run/user/$(id -u) ~/projects/agent-fabric/runtime/claude-code/bootstrap.sh'`
(the host executor's environment is empty, so `systemctl --user` needs
the runtime dir spelled out). A daemon restarts itself on a pull of its
source; a request posted while it was down is never answered (it primes
from the newest record). CI runs as `runner`: never assert this host's
login in a test (64ef9ba). See [[blind-review-loop]].

*References: blind-review-loop*

*Observed 2026-09-17 (fabric-coordinator)*

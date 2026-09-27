# The control plane: a daemon per account, a channel on the relay, `fabric-ctl`

Moved to [agent-fabric ADR-029](adr/ADR-029-the-control-plane-a-control-agent-per-account.md) — every account runs a control agent that answers the operator's requests on a relay channel no session drains; reads are fenced, actions signed.
If a file, prompt, skill or message sent you here, update that reference to point directly at `docs/adr/ADR-029-the-control-plane-a-control-agent-per-account.md` (from another repository: "agent-fabric ADR-029"). This file is removed once nothing cites it.

# Fabric commands run by name, without an approval

Moved to [agent-fabric ADR-009](adr/ADR-009-fleet-operations-are-signed-control-plane-actions.md) — every session-facing fabric command is listed in commands.json, linked into ~/.local/bin and allowed by name, never run through $AGENT_FABRIC_ROOT.
If a file, prompt, skill or message sent you here, update that reference to point directly at `docs/adr/ADR-009-fleet-operations-are-signed-control-plane-actions.md` (from another repository: "agent-fabric ADR-009"). This file is removed once nothing cites it.

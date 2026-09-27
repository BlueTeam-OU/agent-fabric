# Per-agent state is one layer — what changed on 2026-09-16

Moved to [agent-fabric ADR-003](adr/ADR-003-per-agent-state-is-one-layer.md) — every write under agents/<login>/ goes through runtime/identity.py, atomic and locked; a binding is per (agent, host).
If a file, prompt, skill or message sent you here, update that reference to point directly at `docs/adr/ADR-003-per-agent-state-is-one-layer.md` (from another repository: "agent-fabric ADR-003"). This file is removed once nothing cites it.

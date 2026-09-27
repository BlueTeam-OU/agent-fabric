# An assignment goes to one login, never to a role — what changed on 2026-09-19

Moved to [agent-fabric ADR-023](adr/ADR-023-an-assignment-goes-to-one-login.md) — a REQUEST, or any message with a REQUEST:, ACCEPTANCE: or DELIVER-TO: section, is addressed TO one login; the validator refuses it TO-ROLE.
If a file, prompt, skill or message sent you here, update that reference to point directly at `docs/adr/ADR-023-an-assignment-goes-to-one-login.md` (from another repository: "agent-fabric ADR-023"). This file is removed once nothing cites it.

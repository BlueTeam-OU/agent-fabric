---
role: "rust-services-dev"
class: solution
topic: "interweave-bridge-host-line-ceiling"
description: "InterWeave claude-channel bounds each host stdin line at 1 MiB before UTF-8/JSON; over-ceiling lines dropped unanswered (PR #330)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bc3303baa20eca76
---

## InterWeave claude-channel bounds each host stdin line at 1 MiB before UTF-8/JSON; over-ceiling lines dropped unanswered (PR #330)

InterWeave `apps/claude-channel/src/host_input.rs`, merged in PR #330 (2a415b91, 2026-10-21): `HostLines` reads the MCP host's stdin under `MAX_HOST_LINE_BYTES` (1 MiB). The ceiling is checked on raw bytes as they arrive.
- A longer line is drained to its newline and never kept. It gets no answer, because its id may sit in the refused bytes.
- A line that is not UTF-8 is dropped. Before the fix it ended the bridge.
- The reader is cancel-safe under the serve loop's `select!`: its state lives in the struct, and its only await is `fill_buf`.
- A `const` assertion holds `6 * MAX_PAYLOAD_BYTES + 64 KiB <= MAX_HOST_LINE_BYTES`. Raising the payload ceiling past about 163 KiB fails the build.
- Recorded in `architecture/plugin/SECURITY.md` "Host input", which is architect-cto's text.
- Evidence is `tests/host_line.rs`: the real binary over pipes, sent a 64 MiB line, peak RSS +1.1 MB. A one-off control with the ceiling lifted gave +201.8 MB; it is not a test.

Open, unproven:
- The line buffer's allocation can reach about 2 MiB, though it holds at most 1 MiB of bytes.
- The 64 KiB envelope allowance is not measured against the other tool arguments' bounds.

#330 armed as a boundary change under 8 work commits, on architect-cto's `AUTHORIZES` (see [[boundary-arm-authorization]]).

*References: boundary-arm-authorization*

*Observed 2026-10-20 (rust-services-dev)*

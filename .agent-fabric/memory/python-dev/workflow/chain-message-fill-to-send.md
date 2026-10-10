---
role: "python-dev"
class: workflow
topic: "chain-message-fill-to-send"
description: "compose → fill → gzcoord-send must be one && chain; a failed fill step otherwise sends the empty skeleton, which the validator accepts"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 158276076f982c73
---

## compose → fill → gzcoord-send must be one && chain; a failed fill step otherwise sends the empty skeleton, which the validator accepts

2026-10-09: I filled a composed OBSERVATION with a python heredoc doing re.sub(..., body, ...); the body held `\Z`,
re.sub read it as a bad template escape and raised, and the next line (gzcoord-send, on its own line, not chained)
sent the skeleton with every section empty (01a11edf). gzcoord-send's validator does not refuse empty sections.
**Why:** a message is published the moment it is sent; an empty one costs the reader a turn and needs a correction.
**How to apply:** `gzcoord-compose … && python3 - … <<'EOF' && gzcoord-send file`, the fill by slicing at the first
section heading (s[:s.index("OBSERVATION:\n")] + body), never re.sub with the body as the replacement.

*Observed 2026-10-09 (python-dev)*

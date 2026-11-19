---
role: "python-dev"
class: domain
topic: "watch-check-assert-whole-contract"
description: "a \"says nothing\" check on a watch must assert exit code, the one stdout line and stderr exactly empty; name a mutation per channel"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5485c40fecb85c93
---

## a "says nothing" check on a watch must assert exit code, the one stdout line and stderr exactly empty; name a mutation per channel

j220/#532 F3 then F6: a check that read stdout only passed a silent early exit and a drop line on stderr; asserting "unreachable" not in stderr still let a relay-back line through. Assert `returncode == 0`, stdout == the quiet line, `err.strip() == ""`.
**Why:** each narrower assertion left a mutation alive; two review rounds for one check.
**How to apply:** for any "says nothing" claim, list every channel and every line the code can print, plant one mutation per channel (stderr redirect of each line) before delivery. Short TMPDIR (a host scratch path) for suites with unix sockets.

*Observed 2026-11-09 (python-dev)*

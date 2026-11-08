---
role: "python-dev"
class: solution
topic: "j112-unresolved-links-merged"
description: "j112 assembler unresolved_links report merged as #473; lint traps (clone-only project-name rule, roots seam), review traps, arm F2 deferral"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5d4a867022076926
---

## j112 assembler unresolved_links report merged as #473; lint traps (clone-only project-name rule, roots seam), review traps, arm F2 deferral

tools/fabric/assembler/links.py + report.py wiring: `unresolved_links` in last-drain-report.json (slice, heading, target, why, in) and an UNRESOLVED LINKS stderr section; merged as #473 (3 work, 2 fix), head 7903dc87, 2026-11-04. Report only, exit unchanged. The lint rule that reads it is the requester's (owed after merge).

**Why:** a link to an undrained memory, another corpus or a misspelled topic shipped silently; the harvest cites every `[[x]]` of a body, code or not (harvest_memory.WIKILINK_RE), so the References line carries code-span links too (review F1).

**How to apply:**
- A project name in a docstring of a generic file passes lint in the checkout but fails `test_roots_readers` (lint in a clone) and the imported-tree lint cases; join instance paths through `roots.memory_dir`, never `os.path.join(root, "memory")` (`test_roots_seam`).
- A mutation test for a regex needs an input where old and new differ: a lone backtick needs a later backtick span in the same paragraph, or the old regex passes too (review F4).
- `fabric-review next --pr` needs the round saved first (`fabric-review save <pr> <n> < report`), and the request's `range:` must be pinned commit ids ending at the previous reviewed head.
- Arm refused on a P3 that a later round never restated a Judgement for: `--defer "<head8>:F<n>" "<why>"`.
- `tests/run.sh` waits on a host-wide full-suite lease; CI's guards-and-suites also runs it.

*References: x*

*Anchors: `tools/fabric/assembler/links.py::unresolved_links`, `tools/fabric/assembler/links.py::without_code`*

*Observed 2026-11-04 (python-dev)*

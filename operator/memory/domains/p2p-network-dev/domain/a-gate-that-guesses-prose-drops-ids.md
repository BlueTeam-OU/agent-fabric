---
role: "p2p-network-dev"
class: domain
topic: "a-gate-that-guesses-prose-drops-ids"
description: "in a refusing gate (licence notices, allow-lists), a heuristic that classifies input as harmless prose by case or shape fails open one shape per review round; fail closed and accept loud false positives"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - ad1ac32e7bb441cd
---

## in a refusing gate (licence notices, allow-lists), a heuristic that classifies input as harmless prose by case or shape fails open one shape per review round; fail closed and accept loud false positives

On #386 (j111, then two review rounds), release_notices.py tried to tell a
wrapped SPDX continuation from a prose line opening on With, And or Or.
The reason was to stop a sentence like "With contributions from…" being
read as ids, a P3 false positive from #381. Each rule failed open on a
new shape, and the id was dropped without an error:
- "id-shaped or known word only" let through `or ( LicenseRef-Frob )`,
  `with LLVM-exception` and `or WTFPL`;
- "only a plain lower-case word is prose" let through `or curl` and
  `or wtfpl`.

SPDX ids and operators are case-insensitive, so no case or shape of the
next word tells an id from prose. The fix (0b9a7279) is that any operator
line, in any case, reads on: prose is refused loudly, and no id passes
unread.

How to apply: in a gate whose job is to refuse, never trade a loud false
positive for a heuristic that can fail open. At the second round on the
same invariant, remove the heuristic instead of adding a shape. Before
committing, diff base, head and new over every probed input
([[rewriting-a-parser-in-review-rounds-regresses-earlier-shapes]],
[[review-loop-same-invariant-escalate]]).

*References: review-loop-same-invariant-escalate, rewriting-a-parser-in-review-rounds-regresses-earlier-shapes*

*Observed 2026-10-23 (p2p-network-dev)*

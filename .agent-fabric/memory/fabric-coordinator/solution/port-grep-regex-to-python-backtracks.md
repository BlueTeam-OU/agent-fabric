---
role: "fabric-coordinator"
class: solution
topic: "port-grep-regex-to-python-backtracks"
description: "Porting a bash guard's grep -E patterns to Python re can turn a linear match exponential; a hook past its timeout is not a refusal"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a592563da9a1e2a2
---

## Porting a bash guard's grep -E patterns to Python re can turn a linear match exponential; a hook past its timeout is not a refusal

grep -E never backtracks; Python's `re` does. When #96 ported
`review-bash-guard.sh` to `review-bash-guard.py` with the patterns
translated mechanically, quantified option groups whose pieces could match
the same text (`git([\s]+-[A-Za-z-]+([\s]+[^\s]+)?)*`: an option's argument
could also be the next option) went exponential: `git` followed by thirty
`\t--` did not finish in two minutes. CodeQL flagged three (alerts 31–33);
a fuzz of every pattern with repeated tokens confirmed them.

A PreToolUse hook that runs past its timeout does not refuse, so for a
fence a slow regex is a bypass, not a performance bug.

**How to apply:** when porting grep patterns to Python, make every repeated
group unambiguous (an argument that cannot start like the next option), fuzz
each pattern with ~3000 repetitions of short tokens in a child with a
timeout, and run a fence's verdict under a time budget that denies when late
(88e5bb7). Related: [[guard-must-catch-the-shape-it-replaced]].

*References: guard-must-catch-the-shape-it-replaced*

*Observed 2026-10-04 (fabric-coordinator)*

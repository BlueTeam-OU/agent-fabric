---
role: "python-dev"
class: domain
topic: "regex-redos-fix-needs-old-new-comparison"
description: "Narrowing a regex to stop backtracking in a refusing validator changes what it accepts; compare old and new exhaustively and pin nested/unbalanced must-refuse cases"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4b303690b3aa255b
---

## Narrowing a regex to stop backtracking in a refusing validator changes what it accepts; compare old and new exhaustively and pin nested/unbalanced must-refuse cases

In #290 the file-link refusal in `tools/fabric/addenda_check.py` (`LINK_RE`) was rewritten three times: CodeQL named a real ReDoS (inner class `[^\]]` also matches `[`); excluding `[` fixed the time but made `see [a [b](../f.md)](https://x)` pass (P1, found by review, not by my tests); the lookahead form still backtracked on runs of `](` until `]` left the destination class.

**Why:** a character-class change that fixes backtracking also changes the language. My controls tested only unnested link text, so the regression was invisible to them. A pattern that derives one thing (the destination) from another (the link text) is the ambiguity; matching each `](` destination on its own, with a lookahead, removes both the ambiguity and the bypass.

**How to apply:** before replacing a pattern in a refusing check, enumerate every string over a small alphabet (`[`, `]`, `(`, `)`, a letter, `.`) up to length ~8 and assert new refuses a superset of what old refused; make nested, two-deep and unclosed-destination variants must-refuse cases; test linearity as a ratio of two sizes, not a wall-clock bound. See [[j55-addenda-p3-delivered]].

*References: j55-addenda-p3-delivered*

*Observed 2026-10-18 (python-dev)*

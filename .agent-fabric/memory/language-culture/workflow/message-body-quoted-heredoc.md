---
role: "language-culture"
class: workflow
topic: "message-body-quoted-heredoc"
description: A GZCoord message body with backticks or $ goes through a quoted heredoc only; substitute a variable afterwards, or the shell eats words and runs code spans
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 62f9f18cc12d0fa4
---

## A GZCoord message body with backticks or $ goes through a quoted heredoc only; substitute a variable afterwards, or the shell eats words and runs code spans

AGENTS.md's quoted-heredoc rule is stated for commit messages; the gzcoord-send skill does not repeat it (checked 2026-10-15). The holes happened in messages: three on 2026-09-18 — the ge holder (01a0b1c3), web-dev (01a0b444: three code spans executed by the shell), and me (01a0b489: the word "venue" lost); each cost a correcting INFO, and gzcoord-send's validator does not see the hole — nor empty sections: on 2026-10-14 I sent an OBSERVATION skeleton with every section empty (01a13a59-21d7) and the filled one 20 s later (01a13a59-9430). Write a message body with backticks or $ through `<<'EOF'`; when a variable is needed, put a placeholder in the text and substitute it as a separate step in the same `&&` chain, then look at the file before sending. Candidate for an executable form (a gzcoord-send warning on empty code spans), to propose to fabric-coordinator.

*References: chain-message-fill-to-send*

*Observed 2026-10-15 (language-culture)*

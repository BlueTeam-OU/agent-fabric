---
role: "language-culture"
class: workflow
topic: "compose-from-project-working-copy"
description: "run gzcoord-compose from the project's working copy, never the scratchpad, or PROJECT and REPOSITORY come out wrong"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a97c2a6b8caaca6b
---

## run gzcoord-compose from the project's working copy, never the scratchpad, or PROJECT and REPOSITORY come out wrong

On 2026-10-21 I ran gzcoord-compose with the scratchpad as cwd for an InterWeave REPLY. It left REPOSITORY out and filled PROJECT: agent-fabric, and gzcoord-send sent it that way.

**Why:** compose takes PROJECT and REPOSITORY from where you stand, not from the thread you answer.

**How to apply:** run compose from the project's working copy (`cd ~/projects/<project> && gzcoord-compose ... -o <scratchpad>/msg.txt`), and grep PROJECT/REPOSITORY in the file before you send. Related: [[name-the-pushed-commit]].

*References: name-the-pushed-commit*

*Observed 2026-10-20 (language-culture)*

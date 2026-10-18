---
role: "language-culture"
class: workflow
topic: "own-addenda-write-refused"
description: auto mode refuses this holder writing its own addendum file for install (Instruction Poisoning); report it and block, do not route around it
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0b5d900219f26f4d
---

## auto mode refuses this holder writing its own addendum file for install (Instruction Poisoning); report it and block, do not route around it

On 2026-10-18 (j65, REQUEST 01a14cd5), I tried to write a re-issued
charter-addendum.md into /var/tmp/holder-addenda/reissue/<login>/. The
only change was the against_digest line. The Claude Code auto-mode
classifier refused the write as "Instruction Poisoning": an agent
writing text that the parent installs into its own launch prompt.

**Why:** the addendum becomes part of this agent's own system prompt,
so even a digest-only edit counts as writing one's own instructions.

**How to apply:** for an addendum re-issue, verify the digests and read
the body read-only (addenda_check.body_digest uses FRONTMATTER_RE
`\A---\n(.*?)\n---\n`). Reply with the findings, block the job, and
leave the write to the owner's decision. Do not write it another way.
See [[addenda-check-before-relaunch]].

*References: addenda-check-before-relaunch*

*Observed 2026-10-18 (language-culture)*

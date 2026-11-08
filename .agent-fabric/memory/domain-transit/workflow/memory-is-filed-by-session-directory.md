---
role: "domain-transit"
class: workflow
topic: "memory-is-filed-by-session-directory"
description: "a memory lands in the corpus of the repository the session stood in, not the one it is about; write a fact about another repo from that repo's session, and no home-directory paths"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 66094a8aeca204ac
---

## a memory lands in the corpus of the repository the session stood in, not the one it is about; write a fact about another repo from that repo's session, and no home-directory paths

The harness files a memory under the project directory of the session that wrote it
(the working copy's main checkout, so a worktree files with its repository), and the
drain takes each directory into that repository's corpus. Anchors and the text naming
another repository change nothing. In the 2026-10-31 drain, a gzapp fact (stop_policy.json
pin) and an agent-fabric fact (fabric tools run from the checkout) written from
[redacted]-shop-transit sessions went into [redacted]-shop-transit's corpus; fabric-coordinator
held both in [redacted]-shop-transit#5 (OBSERVATION 01a19f54-2a29-7ddf-8d2f-f2a038d00434).
Two gzapp-anchored memories written from agent-fabric sessions had already reached
agent-fabric's corpus the same way. Moved on 2026-11-03 (job j27).

**Why:** a slice in the wrong corpus is invisible where it applies and noise where it
lands; a public repository must also not carry a login's home-directory paths.
**How to apply:** before writing a memory, check which repository its facts concern;
if not the one the session stands in, write it in that repository's memory directory
(the harness's per-project directory beside this one). Describe paths relative to a
repository or as "the agent-fabric checkout", never under a home directory.

*Anchors: `memory/README.md::<launch-dir-slug>/memory/`*

*Observed 2026-11-03 (domain-transit)*

---
role: "fabric-coordinator"
class: workflow
topic: "memory-corpus-is-wisdom"
description: "The owner's framing of the curated memory corpus (2026-10-10): wisdom, not memory; happened facts live in git, PRs, ADRs, job logs and GZCoord; superseded knowledge is the slice's git history"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2e178570be7c965f
---

## The owner's framing of the curated memory corpus (2026-10-10): wisdom, not memory; happened facts live in git, PRs, ADRs, job logs and GZCoord; superseded knowledge is the slice's git history

The owner, 2026-10-10, while weighing third-party memory systems: "our long term curated
memory is more about wisdom than memory"; "we have a different mechanism for keep track
of happened fact"; "superseded knowledge in our system become git history".

**Why:** the corpus holds distilled, judged lessons (how to work, why, what to watch
for). Events, decisions and who-did-what already have their authority: git history, PRs
and reviews, ADRs, `fabric-jobs` logs, the GZCoord relay; and the fabric already has an episodic tier,
each agent's exact GZCoord message history in `episodic.db` (agent-fabric ADR-041), which
the owner calls the events memory. A replaced slice section stays
readable in `git log` of its file.

**How to apply:** when borrowing from other memory systems, reject episodic capture,
timelines and bi-temporal fact stores (Zep "valid until") as non-gaps (the episodic store
may feed the drain as input); look for what
improves distilling lessons, keeping them true against the tree, and finding the right
one at the right moment. Related: [[claude-mem-and-recall-zero]].

**Adopted direction (the owner, 2026-10-10):** a reflection pass over `episodic.db` that
turns what an agent was told and corrected on into candidate lessons for the drain. Shape
that fits ADR-041: run by the agent itself (rule 1: the journal is its own), output into
its own Claude memory with a `roles_class`, promoted only through the drain (rule 8),
history treated as evidence and credential-shaped values withheld (rule 7). Job j89.

**The journal is kept, never pruned (the owner, 2026-10-10):** "journal items are not
removed because they feed long term memory - that must remain in that way". Today no code
deletes from `episodic.db` and ADR-041 has no retention rule, but none forbids it either;
the memory plan writes it down as a rule. A reflection pass reads with a cursor and
never consumes rows. Measured the same day: all 25 journals fed, 1,276 direct messages
(10-06..10-10) all present at both ends, no bypass lines; the journal holds GZCoord
messages only, so owner prompts in a session are not in it.

**Plan approved 2026-10-10** (master plan, section "Memory: wisdom kept true, found when it
matters"): P0 cleanup drain first; P1 ADR-049 amended (registration via
runtime/mcp/fabric-memory/install.py into ~/.claude.json, memory_mark, score bands, shared
memory_index.py); P2 ADR-050 — truth judged where it lives: mechanical anchor checks
anywhere, the owning role verifies (a job on its agent), the reader marks; the drain adds
only an advisory model hint (the owner chose "distributed, plus a central assist" after
asking "are you proposing to centralise the evaluation of slice truthness?"); P3 the
session reflects at job end on its own context plus fabric-history, journal append-only
by rule; P4 the recall hook only after a week of call-log numbers.

*References: claude-mem-and-recall-zero*

*Observed 2026-10-10 (fabric-coordinator)*

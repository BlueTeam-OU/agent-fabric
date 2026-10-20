# ADR-050 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-20 — An anchor may name its project

language-culture-en reported (REPLY 369884) that memories drained in
agent-fabric cite paths in blueteam.ee and gzapp, and memory_check judged
every anchor in the slice's origin project: each such anchor read
stale-hard although its file stood in the other repository. Decided by
fabric-coordinator (job j307): an anchor may name its project by its
registry id, `<project>:<path>`, and is judged in that project's checkout;
when that checkout is absent the section is unchecked, never stale. An
unnamed path is the origin project's, as before, so no anchor already
written changes meaning. The single colon cannot be confused with `::`,
and a path segment never held a colon before (the schema refused one).

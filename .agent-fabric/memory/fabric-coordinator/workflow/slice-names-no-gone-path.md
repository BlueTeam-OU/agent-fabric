---
role: "fabric-coordinator"
class: workflow
topic: "slice-names-no-gone-path"
description: "A drain-bound memory never names a path that is gone, not even to say it is gone: memory_check reads every cited path and flags the section stale-hard for ever"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ee76cf20beb30ef5
---

## A drain-bound memory never names a path that is gone, not even to say it is gone: memory_check reads every cited path and flags the section stale-hard for ever

j306 (2026-10-23): of the 16 sections flagged in my corpus, 9 were true and stale-hard only because their text
said that some retired file, named by its path, is gone.
`tools/fabric/memory_check.py` takes every path-shaped string whose top directory the tree has (`CANDIDATE`,
`cited`) and cannot tell "X is gone" from "X does", so such a section is re-flagged at every drain. The
corrections written on 2026-10-11 had made it worse by adding the retirement history.

**Why:** the history of what was removed is git's record ([[memory-corpus-is-wisdom]]); in a slice it only
costs a flag. The checker over-reports on purpose ([[lint-overreport-not-model]]).

**How to apply:** write the current truth only. Name another repository's file by an anchor
`<project>:<path>::<literal>`, never as a bare path in the body. Before writing a correction, run its text
through `memory_check.cited` against the tree. A merge_target holding a gone path is fine: it is metadata, not
section text.

*References: lint-overreport-not-model, memory-corpus-is-wisdom*

*Anchors: `tools/fabric/memory_check.py::CANDIDATE`*

*Observed 2026-10-23 (fabric-coordinator)*

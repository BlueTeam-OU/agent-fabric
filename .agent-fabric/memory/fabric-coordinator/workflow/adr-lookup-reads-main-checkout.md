---
role: "fabric-coordinator"
class: workflow
topic: "adr-lookup-reads-main-checkout"
description: "checking a DIGEST bullet you just wrote with bare `fabric-adr lookup` reports \"no DIGEST entry\" — it reads the main checkout, not the worktree"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 449c48094074040e
---

## checking a DIGEST bullet you just wrote with bare `fabric-adr lookup` reports "no DIGEST entry" — it reads the main checkout, not the worktree

On j479 (2026-10-31, ADR-003 "a lock file is not state", commit on the j444 branch), `fabric-adr lookup "lock file"`
answered "no DIGEST entry mentions all of that" even with `AGENT_FABRIC_ROOT=$PWD`. Running
`python3 tools/fabric/adr.py lookup ...` from the worktree found the new bullet. So when you trim a DIGEST entry, use the
worktree's adr.py to confirm that each dropped keyword still matches (see [[digest-entry-over-250-words]],
[[digest-trim-keeps-lookups]]).

The lock-file decision itself: a file opened `O_CREAT` only to hold a `flock` is outside rule 1 on three conditions:
it is never written or read, it is opened without `O_TRUNC` and mode 0600, and it is never removed or replaced.
`O_NOFOLLOW` and `O_CLOEXEC` are good practice, not conditions, because `agent_lock` predates them. The follow-up j487 covers the hooks'
own tmp+rename writers of session-state.json and session-context.json.

*References: digest-entry-over-250-words, digest-trim-keeps-lookups*

*Anchors: `tools/fabric/adr.py::cmd_lookup`, `tools/fabric/control/busy.py::O_CREAT`*

*Observed 2026-10-31 (fabric-coordinator)*

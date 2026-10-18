---
role: "fabric-coordinator"
class: workflow
topic: "readded-job-check-tree-first"
description: "A job re-added after a drop may already be delivered under another job; read origin/main and the jobs it spawned before starting it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3a7903f227e47f35
---

## A job re-added after a drop may already be delivered under another job; read origin/main and the jobs it spawned before starting it

j195 (re-added 2026-10-14 as j89's replacement, "Record: reflection pass over episodic.db") was
already delivered when its session started 2026-10-15: ADR-058 accepted and on origin/main
(06612ee2, ac8a6cf5), `fabric-reflect` built in #264, its build remainder already queued as j215,
and the "upkeep survey" half had become ADR-050 (accepted 2026-10-13, build in j196). The job was
still marked blocked on its request to python-dev-02 although that request was answered (#256
closed, folded into #264).

**Why:** a re-added job keeps its old title, not the progress made under other jobs since; working
it from the title duplicates landed work.
**How to apply:** before starting a re-added or long-blocked job, `git log origin/main` for its
topic, read the thread it blocks on (`fabric-history --thread <id>`), and grep `fabric-jobs list
--all` for successor jobs; if it has landed, close it with the commit as evidence and take the
next. Related: [[memory-work-closed-2026-10-14]].

*References: memory-work-closed-2026-10-14*

*Anchors: `docs/adr/ADR-058-reflection-pass-over-the-journal.md::Accepted`, `bin/fabric-jobs`*

*Observed 2026-10-15 (fabric-coordinator)*

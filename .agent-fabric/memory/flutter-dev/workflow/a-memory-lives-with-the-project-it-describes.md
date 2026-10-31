---
role: "flutter-dev"
class: workflow
topic: "a-memory-lives-with-the-project-it-describes"
description: "Write a memory into the memory directory of the project it is about, not the session's starting one — the drain stamps that directory's project as its origin and checks its anchors there"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2ca2de80b513ed21
---

## Write a memory into the memory directory of the project it is about, not the session's starting one — the drain stamps that directory's project as its origin and checks its anchors there

Two of my workflow slices about gzapp (copy REQUESTs; supply hand-offs) were drained
with origin project agent-fabric, because I wrote them in
`~/.claude/projects/-home-flutter-dev-01-projects-agent-fabric/memory/` — the harness's
directory for a session STARTED in agent-fabric, though the work was in the gzapp
clone. ADR-050's check resolves anchors in the origin project's checkout, so their
gzapp anchors (`product/i18n/en-US.json`, `.claude/skills/owed-supply/SKILL.md`) read
as "path gone" and came back to me as stale-hard (REQUEST 01a157cb, 2026-10-20) while
the claims were true.

**Why:** the harness picks the memory directory from the session's cwd at launch,
not from the repository the memory describes; the drain trusts the directory.

**How to apply:** a memory about gzapp code, copy or procedure goes to
`~/.claude/projects/-home-flutter-dev-01-projects-gzapp/memory/` (and its MEMORY.md),
whatever directory the session started in; this one is for the fabric and the role
in general. A misfiled memory is moved, and its drained section retired with an
empty `merge_target` memory in the old directory.

*Anchors: `docs/adr/ADR-050-keeping-wisdom-true.md::origin project's checkout`*

*Observed 2026-10-20 (flutter-dev)*

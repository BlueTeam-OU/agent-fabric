---
role: "fabric-coordinator"
class: threads
topic: "frontmatter-origin-not-redacted"
description: "this corpus's slices carry the project id in origin frontmatter (project, working_copy), which gzapp's \\b<city>\\b ban matches; the assembler redacts bodies and titles, not origin"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "kutaisi-shop-transit"
    working_copy: "kutaisi-shop-transit"
derived_from:
  - 834d83e7f738a10d
---

## this corpus's slices carry the project id in origin frontmatter (project, working_copy), which gzapp's \b<city>\b ban matches; the assembler redacts bodies and titles, not origin

The round-3 blind review of <city>-shop-transit #5 (head 8b419c40, 2026-11-09, job j661) flagged a pre-existing problem. Both domain-transit slices carry `project:` and `working_copy:` set to the repository's own id in their origin frontmatter. gzapp's hygiene list bans the city name (`\b…\b`, flag `i`), and that pattern matches at the hyphen. The assembler redacts topics, titles and bodies, but not origin metadata. Lint at agent-fabric 426ab783 still reports clean.

The repository's public name is the same string, so nothing leaks. It is a gap between what the hygiene rule says and what the assembler does.

Open question for fabric-coordinator: should a project's own id be exempt (`"scope": "others"` on the gzapp entry, or an origin exemption), or should origin be redacted too? Decide it in the assembler, never by hand-editing a slice. Related: [[drain-fabric-worktree-beside-projects]].

**Why:** gzapp's ban is global (it has no `scope: others`), so every project's corpus is held to it, this one included.
**How to apply:** do not "fix" the frontmatter in a drain PR. Raise it with the hygiene-scope decision (job j679 covers the assembler's hygiene loading).

*References: drain-fabric-worktree-beside-projects*

*Observed 2026-11-09 (fabric-coordinator)*

---
role: "brand-comms"
class: workflow
topic: "draining-memory-no-urls-or-host-paths"
description: "Writing a memory that carries a roles_class — no claude.ai share URL, no host path, no [[link]] to a memory that does not drain"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2c90ac4c380fe4f8
---

## Writing a memory that carries a roles_class — no claude.ai share URL, no host path, no [[link]] to a memory that does not drain

A memory with a `roles_class` becomes a slice in a project's corpus, read
on every host and by every role. In it, name an artifact by its title
(and version, if one was recorded), never by its claude.ai link; name a
clone by its repository (`gzapi-org/gzapi.brand`), never by a `~/` or
`/home/` path; and link `[[name]]` only to a memory that also carries a
`roles_class` *and sits in the same project's memory directory*, since
each project drains to its own corpus — a link across projects dangles
as surely as one to a private memory.

**Why:** fabric-coordinator retired brand-comms' interweave-icon thread slice
for a share URL and a host path, and the blind review of gzapi.ge#27
(review 5732971116, 2026-11-02) then found the same in two more slices
plus a link to blueteam-ee-assigned, which has no roles_class (REQUEST
01a19b06-eb02, job j42); blueteam.ee#16's review found blueteam.ee slices
linking gzapp.decks memories (OBSERVATION 01a19d23-d821, 2026-11-02).

**How to apply:** before saving a draining memory, grep it for
`claude.ai/`, `~/`, `/home/` and every `[[…]]` target's `roles_class`.
A tool that lives only at a host path is described by what it does and
who keeps it, not where it sits.

*References: name, …*

*Anchors: `agent-fabric:memory/README.md::roles_class`*

*Observed 2026-11-02 (brand-comms)*

---
role: "p2p-network-dev"
class: workflow
topic: "a-behaviour-change-sweeps-the-prose-that-names-it"
description: After a review fix changes behaviour (an event renamed, a ranking changed, a name made distinct), git grep the old claim across code comments AND the architecture docs before arming; fix your own lane, send the owner of each other line…
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3555553dc19df9af
---

## After a review fix changes behaviour (an event renamed, a ranking changed, a name made distinct), git grep the old claim across code comments AND the architecture docs before arming; fix your own lane, send the owner of each other line its path:line, then check their rewrite against the code

The pattern recurred at least four times in InterWeave (2026-09-26..30):
review fixes made freshly merged record text wrong — a rule that said a
failed rebuild "is reported as MdnsUnavailable" after the fix emitted
`MdnsRebuildFailed`; CONNECTIVITY.md saying "known-good first" after the
ranking became "recently good first"; a socket rename applied to one
contract line and missed in the ADR, the digest and a second contract. The
architecture owner's ruling (DECISION 01a0dc05): a record naming one event
while the code emits another must not sit on main even between two merges —
hold the arm until the supplied text is on the branch and re-reviewed. And
the owner's rewrite was itself wrong once ("never-successful last" where the
code ranks by failure count), so read it against the code before folding.

**How to apply:** for every behaviour a review fix changes, `git grep` the
old term, event name or ranking phrase over the code and the architecture
tree; fix code comments yourself; send one OBSERVATION/REQUEST listing each
other-lane line with path:line and the true statement; give the request an
acceptance grep (e.g. `grep -rn -- '<old name>' architecture/` returns only
dated history); fold the supplied commit before arming.

*Observed 2026-10-18 (p2p-network-dev)*

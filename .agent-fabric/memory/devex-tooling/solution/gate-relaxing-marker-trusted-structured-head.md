---
role: "devex-tooling"
class: solution
topic: "gate-relaxing-marker-trusted-structured-head"
description: "a marker or message that lets a gate pass (a waiver, an 'engine unavailable' review, an evidence header) counts only as a structured field, bound to the exact head and repository, from the authorized poster, kept out of every coverage…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 97cd6b500e490160
---

## a marker or message that lets a gate pass (a waiver, an 'engine unavailable' review, an evidence header) counts only as a structured field, bound to the exact head and repository, from the authorized poster, kept out of every coverage bucket; anything else fails closed

Three gates in the arm/review toolkit (2026-10-04..14) each first read a relaxing signal too
loosely:

- **The boundary waiver.** The first reader accepted any DECISION or REPLY whose text named `#<n>`,
  so "I do NOT waive #7" counted. Nothing tied it to a head or a repository, and FROM is only a
  claim on the relay. It became the `WAIVES: <owner/repo>#<n>@<head sha>` metadata field, addressed
  TO the arming login only. The sha must prefix the current head, the role holder is checked by
  presence, and a self-waiver is refused.
- **The codex "unavailable" marker.** Any account could post it, and verdicts.classify put an
  unmarked review by a trusted non-author into `independent`, so the statement covered the head.
  It now counts only as the first line of a review object on that head, with the full sha, from
  the PR author or AGENT_FABRIC_REVIEW_POSTERS. It is taken out before the marked/unmarked split,
  so it never lands in a coverage bucket.
- **The dispatch evidence header.** post-review refuses a report whose header says
  `working-tree`, and refuses a header it cannot read, including one in a blockquote or list item
  or of another version. It strips every header before posting, so session and job ids never
  reach GitHub.

**How to apply:** when a gate gains a way to pass, write down the threat model before the parser:
who can write the signal, which head and repository it binds to, and where else in the pipeline
the same text could be counted. Read the signal only from a field the approver writes on purpose
(metadata or a strict first line), never from prose. Fail closed on any shape not recognised.
Over-refusing is safe, because the author can fix the text and post again. Keep one parser for
the grammar ([[one-format-one-parser]]).

*References: one-format-one-parser*

*Anchors: `tools/fabric/github/arm.py::WAIVES`, `tools/fabric/github/review_status/verdicts.py::def unavailable_of`, `tools/fabric/github/post_review.py::DISPATCH_FENCE`*

*Observed 2026-10-22 (devex-tooling)*

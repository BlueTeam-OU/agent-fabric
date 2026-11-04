---
role: "devex-tooling"
class: workflow
topic: "sibling-file-header-carries-sibling-reason"
description: "files generated from one sibling (forwarder tests, wrapper headers) inherit its why-comment, which is false for the others; read each file's claims from its own target's code"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e2384bbab45d27b9
---

## files generated from one sibling (forwarder tests, wrapper headers) inherit its why-comment, which is false for the others; read each file's claims from its own target's code

InterWeave review tools, 2026-09-25. I generated the forwarder tests for pr-sessions.sh and
pr-review-status.sh from pr-reply's. Each kept pr-reply's reason for passing stdin through
untouched: "a reply body must not be altered". Neither fabric script reads stdin. Review F2 caught
it. My fix (9fea0db4) swapped in another shared sentence, which was false the same way: it named
arguments one script does not take, and said "every tools/gh script" where two are not
forwarders. Re-review N1 caught that. Only b7cac24d, where each header's argument list was read
from that fabric script's own parser loop, held.

**Why:** a comment is the one part of a copied file that no test reads. The assertions passed in
all three rounds, and only the comment was wrong.

**How to apply:** when making N files from one template, list each claim the template's comments
make (what it reads, which flags, why), and check each against that target's own source before
committing. A sentence that appears byte-identical in two of them is a flag to re-derive it, not
proof that it is true. When a review finds this in one file, check every sibling in the same fix:
fix the rule, not the instance.

*Anchors: `tools/fabric/github/pr_sessions.py::--session`*

*Observed 2026-10-22 (devex-tooling)*

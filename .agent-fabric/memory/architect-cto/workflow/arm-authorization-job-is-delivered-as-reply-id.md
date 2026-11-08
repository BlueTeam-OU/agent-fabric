---
role: "architect-cto"
class: workflow
topic: "arm-authorization-job-is-delivered-as-reply-id"
description: "An arming authorization answered over GZCoord is a job delivered with `reply:<MESSAGE-ID>`, never `gzcoord:<id>`; the AUTHORIZES header rides a REPLY to a QUESTION as well as a DECISION, and vouches for one head only"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 69d0726d0ea94d3e
---

## An arming authorization answered over GZCoord is a job delivered with `reply:<MESSAGE-ID>`, never `gzcoord:<id>`; the AUTHORIZES header rides a REPLY to a QUESTION as well as a DECISION, and vouches for one head only

On 2026-11-03 fabric-coordinator asked three times, by QUESTION with
REPLY-EXPECTED: yes, for gzapp #1205's arm below the minimum, once per
head (cf3982a3, e86dce9d5, e24f8865), and devex-tooling once by REQUEST
for InterWeave #530@1cd8a8fe. Each answer is one REPLY whose metadata
carries `AUTHORIZES: <org/repo>#<n>@<full sha>` beside `TO:`, after
reading the remote head's commits, kinds, paths, posted review and gate
myself (`fabric-pr gate <n>` in that project's copy; the index at
index.crates.io for a lock-file bump's yank and checksum claims).

**Why:** `fabric-jobs switch` refuses to leave a delivered job whose
artifact is `gzcoord:<id>`: the accepted forms are a PR, a commit, a
branch on origin or `reply:<MESSAGE-ID>` (the reply's id or the id it
answers). A re-asked head means a new word; the old one lapses with
the head, so each ask is its own job, delivered with its own reply id.

**How to apply:** `fabric-jobs add --request <id>` (title comes from
the message), `start`, verify, send, `deliver j<n> reply:<sent id>`,
`switch`. Related: [[auto-mode-classifier-refuses-authorizes-send]].

*References: auto-mode-classifier-refuses-authorizes-send*

*Observed 2026-11-03 (architect-cto)*

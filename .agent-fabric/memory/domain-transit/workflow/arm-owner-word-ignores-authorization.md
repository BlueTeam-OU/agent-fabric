---
role: "domain-transit"
class: workflow
topic: "arm-owner-word-ignores-authorization"
description: "arming below the minimum on a coordinator DECISION carrying the owner's word — --basis is what counts; --authorization is not read"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 753ead79d9f9b1c9
---

## arming below the minimum on a coordinator DECISION carrying the owner's word — --basis is what counts; --authorization is not read

`fabric-pr arm <n>` requires `--basis` even for `--dry-run`. When the owner's
word reaches me as a fabric-coordinator DECISION with `AUTHORIZES: repo#n@head`,
`--basis "the owner's word"` is what lifts the count rule; the `--authorization
<id>` the DECISION suggests is reported "not needed … not read, and not recorded"
([redacted]-shop-transit #4, 2026-11-01: 2 work commits, minimum 8, armed and merged
on head 547130d1). Still check the DECISION's head equals the PR head first —
arm does not check it for me on this path.

**Why:** the authorization header is for a repository's arming-authority role,
not for the owner's word.
**How to apply:** verify head == AUTHORIZES head, cite the message id in the basis
text, and drop `--authorization`. Related: [[arm-needs-required-checks-in-ruleset]].

*References: arm-needs-required-checks-in-ruleset*

*Anchors: `agent-fabric:tools/fabric/github/arm.py::is not read, and not recorded`*

*Observed 2026-11-01 (domain-transit)*

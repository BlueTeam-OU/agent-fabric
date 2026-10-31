---
role: "fabric-coordinator"
class: workflow
topic: "arm-word-authorizes-line"
description: "How I give a contributor my arm word for a security-boundary PR under the minimum — an AUTHORIZES metadata line in a REPLY, head-pinned"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1462857a6208ce59
---

## How I give a contributor my arm word for a security-boundary PR under the minimum — an AUTHORIZES metadata line in a REPLY, head-pinned

`fabric-pr arm` refuses a security-boundary PR with fewer than 8 work commits unless it has the owner's word or fabric-coordinator's. To give mine to the PR's author, I send a REPLY `TO` that author with a metadata line `AUTHORIZES: BlueTeam-OU/agent-fabric#<n>@<head8>` beside REPLY-EXPECTED. They pass the message id with `--authorization`. This worked on 2026-10-30 for #431: message 01a18d70, merged on 1aafa007.

Before giving it, read the gate (checks, review on the head, threads) and the boundary files' diff myself. The word holds for that head only. A new head needs a new word.

**Why:** a dry-run with `--any-owner` from my session prints the exact field. Arming it myself would arm another session's PR.
**How to apply:** after their merge, distribution (`fabric-ctl all upgrade fabric`) is mine. My own account shows "no answer" in that run; read it back with `fabric-ctl user fabric`. Related: [[own-account-upgrade]], [[arming-prs]].

2026-10-31, #441: I put `AUTHORIZES:` in the REPLY body and `fabric-pr arm --authorization` refused it (verify_grant reads the metadata block only). Insert it after compose, ABOVE `SUBJECT:` (gzcoord-compose has no flag for it); `head -12` the file before sending.

*References: arming-prs, own-account-upgrade*

*Anchors: `tools/fabric/github/arm.py::AUTHORIZES`*

*Observed 2026-10-30 (fabric-coordinator)*

---
role: "fabric-coordinator"
class: workflow
topic: "arm-word-authorizes-line"
description: "How I give a contributor my arm word for a security-boundary PR under the minimum — an AUTHORIZES metadata line in a REPLY, head-pinned"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1462857a6208ce59
  - 335797b4a103c1b1
---

## How I give a contributor my arm word for a security-boundary PR under the minimum — an AUTHORIZES metadata line in a REPLY, head-pinned

`fabric-pr arm` refuses a security-boundary PR with fewer than 8 work commits unless it has the owner's word or fabric-coordinator's. To give mine to the PR's author, I send a REPLY `TO` that author with a metadata line `AUTHORIZES: BlueTeam-OU/agent-fabric#<n>@<head8>` beside REPLY-EXPECTED. They pass the message id with `--authorization`. This worked on 2026-10-30 for #431: message 01a18d70, merged on 1aafa007.

Before giving it, read the gate (checks, review on the head, threads) and the boundary files' diff myself. The word holds for that head only. A new head needs a new word.

**Why:** a dry-run with `--any-owner` from my session prints the exact field. Arming it myself would arm another session's PR.
**How to apply:** after their merge, distribution (`fabric-ctl all upgrade fabric`) is mine. My own account shows "no answer" in that run; read it back with `fabric-ctl user fabric`. Related: [[own-account-upgrade]], [[arming-prs]].

2026-10-31, #441: I put `AUTHORIZES:` in the REPLY body and `fabric-pr arm --authorization` refused it (verify_grant reads the metadata block only). Insert it after compose, ABOVE `SUBJECT:` (gzcoord-compose has no flag for it); `head -12` the file before sending.

2026-11-03, #461: the same, body line refused (01a19ec1); resent as a header (01a19ec3), armed and merged on 8178f358.

2026-11-09, #533: the same mistake a second time, with this note in the index; python-dev-01 refused and asked again (01a1c186). Bitten twice, so it is a fence now: job for a `gzcoord-compose --authorizes` flag, and `gzcoord-send` warning on an AUTHORIZES line in a body.

2026-11-10: the fence landed as BlueTeam-OU/agent-fabric#540 (python-dev-02's j133; my j714 closed on it). Now: `gzcoord-compose REPLY --to <login> --in-reply-to <id> --authorizes <owner>/<repo>#<n>@<full sha>` writes the header (it refuses a type other than DECISION/REPLY and a role/broadcast target); `gzcoord-send` warns on an AUTHORIZES line in a section. First live use: #547 grant, message 01a1c4a3-a677. Not yet read back by `fabric-pr arm --dry-run --authorization` (j743's fresh session does it).

*References: arming-prs, own-account-upgrade*

*Anchors: `tools/fabric/github/arm.py::AUTHORIZES`*

*Observed 2026-10-30 (fabric-coordinator)*

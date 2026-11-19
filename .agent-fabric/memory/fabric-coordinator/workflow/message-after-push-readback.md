---
role: "fabric-coordinator"
class: workflow
topic: "message-after-push-readback"
description: "Never send \"pushed <sha>\" in the same chained command as the commit and push; read the remote ref back first, a refused commit leaves the old head"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2b7409f629dc8784
---

## Never send "pushed <sha>" in the same chained command as the commit and push; read the remote ref back first, a refused commit leaves the old head

On 2026-11-15 I chained commit && push && compose-and-send in one command for #620. The ADR staged-check refused the commit (a body edit with no Amendments row and no `ADR-Editorial:` trailer), so nothing was pushed. But the message still went out, naming the branch's old head 09f17945 as my commit. A correction followed (REPLY 01a1dddd); the real commit was 9e05a19d.

**Why:** `&&` stopped the push but not the message, which sat after a `;`, and `git rev-parse HEAD` printed the old head.
**How to apply:** send the "pushed" message only in a later command, after `git ls-remote origin refs/heads/<branch>` shows the new sha. A same-PR correction of a decision record's wording takes `ADR-Editorial: corrects this PR's own <date> amendment of <rule> before merge`.

*Anchors: `tools/fabric/adr.py::ADR-Editorial`*

*Observed 2026-11-15 (fabric-coordinator)*

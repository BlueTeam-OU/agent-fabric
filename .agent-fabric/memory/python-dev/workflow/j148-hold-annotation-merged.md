---
role: "python-dev"
class: workflow
topic: "j148-hold-annotation-merged"
description: "j148 #603 merged (08564d8e); brief range must start at the merge-base, not origin/main, or post-review refuses"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ac945e21d1f843e7
---

## j148 #603 merged (08564d8e); brief range must start at the merge-base, not origin/main, or post-review refuses

#603 (annotation admits None, assert not once) merged 2026-11-14; agentd.py is a boundary path, armed on the owner's word at 1 work commit.

**Why:** a brief with `range: origin/main..<head>` pins base_sha to origin/main; when main moved past the branch point, `fabric-pr post-review` refuses ("base is not an ancestor of head") and the review is wasted.
**How to apply:** set the request's range to `$(git merge-base HEAD origin/main)..<head>` before `fabric-review brief`. Also: `rm` of a `$TMPDIR/...` path is refused by the classifier; use a literal path or leave scratch files in the scratchpad.

*Observed 2026-11-14 (python-dev)*

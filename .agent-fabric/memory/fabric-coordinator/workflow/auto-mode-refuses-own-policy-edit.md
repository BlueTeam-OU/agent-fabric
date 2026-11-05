---
role: "fabric-coordinator"
class: workflow
topic: "auto-mode-refuses-own-policy-edit"
description: "editing policies/auto-mode.json from a session is refused by the auto-mode classifier as self-modification"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 04ffb318e039de78
---

## editing policies/auto-mode.json from a session is refused by the auto-mode classifier as self-modification

2026-11-04 (j588, folding jobs into the j596 PR): a scripted edit widening the cleanup allow entry in
policies/auto-mode.json was refused by the auto-mode classifier as [Self-Modification] — the file
governs this session's own permissions. Same family as [[auto-mode-refuses-account-assign]].

**Why:** the classifier treats a change to the rules it applies as the session widening itself;
working around it (another tool, another file) is exactly what it forbids.

**How to apply:** an auto-mode.json change is the owner's to approve in the session (a permission
rule) or to make by hand; say so in the report with the exact text wanted, and go on with the rest.

*References: auto-mode-refuses-account-assign*

*Anchors: `policies/auto-mode.json::Removing, at the end of a job`*

*Observed 2026-11-04 (fabric-coordinator)*

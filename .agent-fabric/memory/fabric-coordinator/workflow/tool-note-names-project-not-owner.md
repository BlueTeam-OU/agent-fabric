---
role: "fabric-coordinator"
class: workflow
topic: "tool-note-names-project-not-owner"
description: "an external-tool review memory names the project, never a personal GitHub owner: 'the <project> repository on GitHub (its author's personal account)'; an organization owner may stay"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d655c3e9727c7311
---

## an external-tool review memory names the project, never a personal GitHub owner: 'the <project> repository on GitHub (its author's personal account)'; an organization owner may stay

2026-11-01, #444 round 1 F1: four of my tool notes (agent-orchestration-standard, open-ontologies,
bndr, paparats-mcp) drained with the owner's personal handle in heading, cue and URL, and one
with a copyright holder's full name. policies/hygiene.json: a person is named by role, never by
name; lint has no pattern for handles, so nothing caught it.
**Why:** a slice travels into every repository; a private person's handle is personal data.
**How to apply:** check the owner first (`gh api users/<owner> --jq .type`): User → write "the
<project> repository on GitHub (its author's personal account)" and drop © lines; Organization →
owner/repo is fine. Related: [[external-tools-evaluated]].

*References: external-tools-evaluated*

*Observed 2026-11-01 (fabric-coordinator)*

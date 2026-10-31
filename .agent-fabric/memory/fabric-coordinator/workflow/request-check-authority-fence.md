---
role: "fabric-coordinator"
class: workflow
topic: "request-check-authority-fence"
description: "Before a REQUEST that edits files, check every path against the assignee's policies/authority.json entry, its excluded list, the never-list and its remit; name the outside paths in the request and supply them myself as commits on its branch"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ee64b9254c1a9909
---

## Before a REQUEST that edits files, check every path against the assignee's policies/authority.json entry, its excluded list, the never-list and its remit; name the outside paths in the request and supply them myself as commits on its branch

Across five weeks of my journal, contributors declined or stalled on my REQUESTs because a named path sat outside their entry: runtime/claude-code/ and runtime/identity.py, tests a role may not commit, `.agent-fabric/`, reflect.py on the never-list, projects/registry.json refused by the commit hook. Retirements and ports were the worst case: ADR text, commands.json, tests/run.sh, ci.yml comments and docs naming deleted paths left the contributor's branch red until I supplied them. New fabric Python goes to python-dev; a domain role writes only the contract.

**Why:** the hook refuses the commit, the branch stays incomplete, and the round trip costs a day.
**How to apply:** before sending, list the files the work touches, read the assignee's entry and remit for each, and write in the REQUEST which paths I supply as commits on its branch, built from the description. Related: [[request-verify-premise-before-sending]], [[data-and-reader-together]].

*References: data-and-reader-together, request-verify-premise-before-sending*

*Observed 2026-10-22 (fabric-coordinator)*

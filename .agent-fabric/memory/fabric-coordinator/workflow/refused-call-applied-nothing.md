---
role: "fabric-coordinator"
class: workflow
topic: "refused-call-applied-nothing"
description: "a Bash call a hook refuses ran none of its parts — an edit bundled with the refused commit is lost; re-read the diff before claiming it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 05fc0dc6d365e385
---

## a Bash call a hook refuses ran none of its parts — an edit bundled with the refused commit is lost; re-read the diff before claiming it

2026-11-09, j674: one Bash call carried a python edit of arm.json (an `arm-process` boundary.changes entry), a check
piped into tail, and the commit. The PreToolUse hook refused the call for the piped check, so the edit never ran
either; I re-ran only the check and the commit, and told python-dev-02 the entry was in 37120860. Their review of
#514 found it missing (F5, P2): lint's arm_boundary_findings refuses a paths change with no changes entry.

**Why:** a refused tool call is all-or-nothing; the parts I meant to keep were part of what was refused.
**How to apply:** after any refused call, `git diff --cached` / `git show --stat HEAD` before committing or claiming;
keep file edits in their own call, separate from the check-and-commit call. Related: [[review-and-guards]].

*References: review-and-guards*

*Anchors: `runtime/claude-code/hooks/job-copy-guard.sh::piped into a filter`*

*Observed 2026-11-09 (fabric-coordinator)*

---
role: "devex-tooling"
class: domain
description: "A custom PreToolUse hook that DENIES known-bad text shapes and stays silent otherwise fails open, not closed — it needs the opposite polarity"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-09-05"
origin:
  - clone_id: "clone-c8407dca40bd40fc"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 7a34648bff6d2e3f
  - 895b73e13000630c
  - c9f3329de953d672
---

## A custom PreToolUse hook that DENIES known-bad text shapes and stays silent otherwise fails open, not closed — it needs the opposite polarity

This repo built and then deliberately disarmed `tools/checks/gh_graphql_mutation_guard.sh`, a PreToolUse hook meant to let `gh api graphql` run queries freely while blocking all but two named mutations. Three independent bypasses were confirmed (a heredoc placed before the real invocation, a GraphQL comment splitting the operation keyword from its body, a shell-quote-split field name like `qu'e'ry=@doc`), and each earlier 'fix' attempt (quote-stripping to find the mutation keyword) introduced a worse hole — stripping shell-quoted spans erased the mutation document itself, letting a quoted destructive mutation sail through as if it were plain text. The structural cause: a hook sees command TEXT before the shell parses it, while what actually executes is the argv the shell produces from that text, and bash can compose one argv in unboundedly many textual spellings. Enumerating spellings to DENY is therefore not a winnable strategy for any hook guarding a structured payload (GraphQL body, SQL, etc.) carried as command text. The correct polarity for this class of guard is to auto-approve one strict canonical shape and stay silent (i.e. fall through to the default prompt) on everything else, so an unrecognised spelling prompts instead of running — never to deny known-bad and default-allow the rest.

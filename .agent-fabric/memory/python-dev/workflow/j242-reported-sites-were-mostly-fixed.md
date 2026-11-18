---
role: "python-dev"
class: workflow
topic: "j242-reported-sites-were-mostly-fixed"
description: "a coordinator's list of raw readers/bare parses was a day old; grep origin/main first, then sweep the class (ast.parse without catch_warnings)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 86e3aad73e0ca59e
---

## a coordinator's list of raw readers/bare parses was a day old; grep origin/main first, then sweep the class (ast.parse without catch_warnings)

j242 (#608): of 7 reported raw binding readers and 3 bare parses, 6 and 2 were already fixed on main; the real leftover was transport_calls.scan (same class, not on the list), found by grepping every `ast.parse(` outside tests. Never-list files (layout, routing, identity, lint_rules/*) go as a `git apply -p1` patch in the REPLY, built in a scratch copy and checked in a scratch worktree with the affected suites and lint.
**Why:** a report's line numbers are late; the class sweep found docs.py and command_names.py too.
**How to apply:** grep the tree at origin/main before planning; post-review needs the report in a file and the bare `fabric-pr post-review N < file`; `fabric-jobs done` takes the artifact as a positional, not --evidence. See [[post-review-bare-and-verbatim]].

*References: post-review-bare-and-verbatim*

*Observed 2026-11-14 (python-dev)*

---
role: "devex-tooling"
class: solution
topic: "guards-wired-one-hop-reading"
description: "guards_wired.py rule 1's one hop — what a wired shell member is read as running, and why it refuses rather than guesses"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ffada829bda887a1
---

## guards_wired.py rule 1's one hop — what a wired shell member is read as running, and why it refuses rather than guesses

guards_wired.py rule 1 counts a member as run when a shell member a
workflow runs directly runs it (fabric-coordinator's ruling 01a15adf,
2026-10-20; built as j186, delivered on
develop-qzapp/devex-tooling/for/user/guards-wired-one-hop at 7c4d7f30,
2026-10-21). The reading is an allow-list, narrower than the ruling's
"any argument": only an interpreter's first operand (bash, sh, python3,
python, harmless flags) or a path command word counts. A script with a
<<, a backtick, an unclosed quote, a ( closing later, a case beside a (,
a # straight after an operator, a $' ' string or a # beside a $( ) is
not read, and stderr names it when it names an unwired member. Its
tests live in tests/test_guards_wired.py, outside devex-tooling's
contributor entry, so they travelled as an inline patch in REPLY
01a15c63-bf83 (seq 403605).

Open follow-up: shell_words.strip_comment starts no comment after an
operator (true;# x), which the workflow-side Runs reader shares.

Related: [[agent-fabric-arm-json-outside-entry]] (outside-entry hunks
go as a diff), [[shell-reader-allow-list-not-parser]].

*References: agent-fabric-arm-json-outside-entry, shell-reader-allow-list-not-parser*

*Anchors: `tools/fabric/github/guards_wired.py::invoked_members`, `tools/fabric/github/guards_wired.py::_closers`*

*Observed 2026-10-21 (devex-tooling)*

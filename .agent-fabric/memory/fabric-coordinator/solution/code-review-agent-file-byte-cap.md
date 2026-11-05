---
role: "fabric-coordinator"
class: solution
topic: "code-review-agent-file-byte-cap"
description: "editing runtime/claude-code/agents/code-review.md — a test caps it at 13500 bytes; write the addition terse"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 49cc8af62dedd8c6
---

## editing runtime/claude-code/agents/code-review.md — a test caps it at 13500 bytes; write the addition terse

tests/test_install_agent_files.py test_body_is_under_the_cap_and_carries_every_section fails code-review.md over
13500 bytes (every byte is paid on every dispatch). 2026-11-01 j520 (#447, c3070c7b): the coverage-default text
first landed at 13732; trimmed to 13498. Put the long form in review_brief.py's COVERAGE_RULE, which has no cap,
and keep the agent file to one or two lines. An ADR amendment also needs `tools/fabric/adr.py index --write`
(index.json + README table) or test_adr fails four cases.

*Observed 2026-11-01 (fabric-coordinator)*

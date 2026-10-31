---
role: "python-dev"
class: solution
topic: "operator-words-in-command-words-j77"
description: "j77 (#354 r1 F1/F2): job-copy guard command_words — operator words are never operands, function/coproc names, in_command_place replaces COMMAND_PLACE; suite takes >30 min"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4d60c32a1e4ee630
---

## j77 (#354 r1 F1/F2): job-copy guard command_words — operator words are never operands, function/coproc names, in_command_place replaces COMMAND_PLACE; suite takes >30 min

In job-copy-guard.py `command_words`, a redirect operand that is an OPERATOR token (the `(` of `>(`/`<(`) is not consumed; `function NAME` skips NAME; `coproc [NAME]` skips NAME only if a compound start follows; `env -` is `-i`. `in_command_place(before)` (tokens + command_words, glued `x=$(` is not a place) replaced the COMMAND_PLACE regex. Mutations that proved the test: operand skip, function, coproc name, env `-`, glued check, always-False.

**Why:** a background command's default timeout is 30 min and kills a full tests/run.sh (~40 min under load); pass `timeout: 7200000`. test_review_bash_guard_cli.py's CPU-spin case flakes under load (alone: passes). Run test files with `python3 tests/x.py`, not unittest/bash.
**How to apply:** for/ delivery as in [[job-copy-guard-command-words-j76]]; the coordinator said suppliers dispatch no review of their own on #354.

*References: job-copy-guard-command-words-j76*

*Observed 2026-10-22 (python-dev)*

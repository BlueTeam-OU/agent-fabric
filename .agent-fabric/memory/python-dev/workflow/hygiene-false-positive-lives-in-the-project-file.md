---
role: "python-dev"
class: workflow
topic: "hygiene-false-positive-lives-in-the-project-file"
description: "a drain redacting a common word is a project's .agent-fabric/hygiene.json entry, not assembler code; and a mutation sed that matches nothing proves nothing"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ca025a6a03116bc7
---

## a drain redacting a common word is a project's .agent-fabric/hygiene.json entry, not assembler code; and a mutation sed that matches nothing proves nothing

j50: "[redacted]" in a drained slice came from gzapp's hygiene.json `[redacted]` entry (flag i), loaded for every project; fetch it with `gh api repos/<org>/<repo>/contents/.agent-fabric/hygiene.json`. The file is fabric-coordinator's: report the case, test against the pattern the test itself states (the file's content moved twice in one day, a case-sensitive fix leaked the name).

**Why:** the first narrowing was wrong; a test that copied it would have agreed with itself.
**How to apply:** state the pattern in the test with a positive control (the name still redacted). After a mutation by sed, check `git diff --stat` shows the change before reading the result: mine matched nothing and "passed" twice. See [[mutation-run-read-rc-not-fail-count]].

*References: mutation-run-read-rc-not-fail-count*

*Observed 2026-10-19 (python-dev)*

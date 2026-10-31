---
role: "language-culture"
class: workflow
topic: "lint-in-worktree-needs-fabric-flag"
description: "in a worktree lint.py reads the main checkout unless --fabric is given — a false lag warning on the old digest"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7f83183edf53bc70
---

## in a worktree lint.py reads the main checkout unless --fabric is given — a false lag warning on the old digest

In a job worktree, `tools/fabric/lint.py` reads locale translations from the `AGENT_FABRIC_ROOT` checkout (the main working copy), not the tree it runs in, so after a digest update it still shows the old "translation lags" warning. To check the branch: `python3 tools/fabric/lint.py --fabric "$PWD" --no-siblings`; for the tests, `AGENT_FABRIC_ROOT="$PWD" python3 tests/test_launch_prompt.py`. Seen 2026-10-16, j65, commit 99326959.

*References: locale-digest-is-body-only*

*Observed 2026-10-16 (language-culture)*

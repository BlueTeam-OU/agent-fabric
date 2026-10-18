---
role: "python-dev"
class: solution
topic: "codeql-clear-text-logging-follows-secrets-store-derivations"
description: "CodeQL py/clear-text-logging-sensitive-data flags a print of anything derived from the secrets store's path or files read (basename, len) — print a literal"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7bdaefeee8fd5d07
---

## CodeQL py/clear-text-logging-sensitive-data flags a print of anything derived from the secrets store's path or files read (basename, len) — print a literal

In agent-fabric #254 (tools/fabric/secret_state.py) CodeQL raised py/clear-text-logging-sensitive-data on a result line that printed the copy's path, then on its basename and a file count (alerts 67, 68). Only a line choosing between two string literals ("written"/"unchanged") cleared it.

**Why:** the rule is a name/flow heuristic from secretstore's store_dir and the files read, not a real secret.
**How to apply:** in secretstore-adjacent CLIs print literals or the user's own argument; keep the path and counts out of stdout; check `gh pr checks` for CodeQL before asking to arm (fabric-pr arm ignores check results).

*Observed 2026-10-15 (python-dev)*

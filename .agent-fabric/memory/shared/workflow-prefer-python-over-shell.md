---
role: shared
class: workflow
topic: "prefer-python-over-shell"
description: "owner 2026-09-29 — write new fabric tooling (and non-trivial ad-hoc logic) in Python, not shell scripts"
tier: 1
knowledge_scope: full
shared_with:
  - "fabric-coordinator"
  - "python-dev"
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2daef4d9679a1131
---

## owner 2026-09-29 — write new fabric tooling (and non-trivial ad-hoc logic) in Python, not shell scripts

The owner said on 2026-09-29: "from now on better if you use python than shell scripts".

**Why:** the shell scripts written today had exactly the bugs Python avoids:
- a `doppler()` function that `command -v` then found instead of the binary;
- a timeout's exit code swallowed by `|| true` and read as "absent";
- regex and exit-code gates spread across `$?` captures;
- quoting in heredocs.

Python's subprocess, exceptions and argparse make each of these explicit.

**How to apply:**
- A new tool or script in agent-fabric is Python, as `tools/fabric/*.py` and `secret_store.py` already are.
- When a shell script needs more than a small fix, port the part being changed to Python rather than extend the shell: a Python entry point, with the shell file kept only as a thin wrapper if callers need its path.
- Ad-hoc logic in a session (parsing, loops with error handling) goes in `python3 - <<'PY'`, not chained shell.
- Existing shell scripts are not rewritten just for this; the port happens when one is next changed substantially.

See [[a-wrong-why-outlives-the-code]].

*References: a-wrong-why-outlives-the-code*

*Observed 2026-09-29 (fabric-coordinator)*

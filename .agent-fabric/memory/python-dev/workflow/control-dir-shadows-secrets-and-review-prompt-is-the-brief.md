---
role: "python-dev"
class: workflow
topic: "control-dir-shadows-secrets-and-review-prompt-is-the-brief"
description: "tools/fabric/control/ has secrets.py, so `import secrets` in control/pool.py breaks when run as a script; a review Agent prompt must be the rendered brief pasted verbatim"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - febfef52992bdfbd
---

## tools/fabric/control/ has secrets.py, so `import secrets` in control/pool.py breaks when run as a script; a review Agent prompt must be the rendered brief pasted verbatim

j87 (#453): `import secrets` in tools/fabric/control/pool.py passed test_control_pool but failed its
"run as a script, directory never shadows the stdlib" case in the full suite, because control/secrets.py
leads sys.path when the file runs as a script. Use `os.urandom(16).hex()` in control/ modules.

Also: I once dispatched the code-review Agent with a placeholder prompt instead of the brief text;
stopped it and redispatched. The prompt must be `fabric-review brief` output, read and pasted verbatim.

**Why:** a single-suite run hides script-mode shadowing; a placeholder prompt gives the reviewer no range.
**How to apply:** run the full suite (not only the touched test files) before the push; paste the brief, never describe it.

*Anchors: `tools/fabric/control/pool.py`*

*Observed 2026-11-01 (python-dev)*

---
role: "python-dev"
class: domain
topic: "git-reads-in-hooks-need-no-lazy-fetch-env"
description: a hook or tool that reads git objects must set GIT_NO_LAZY_FETCH=1 and GIT_TERMINAL_PROMPT=0, and treat an unreadable object as unknown
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2c54310a8788b97c
---

## a hook or tool that reads git objects must set GIT_NO_LAZY_FETCH=1 and GIT_TERMINAL_PROMPT=0, and treat an unreadable object as unknown

In a partial clone (blob:none, tree:0) a plain `git show`/`ls-tree` fetches a missing object unasked and waits on the network. j110 (#562 F1): memory-write-check's `_git` ran with the session env. Fix: add GIT_NO_LAZY_FETCH=1 and GIT_TERMINAL_PROMPT=0 on top of os.environ (git needs HOME/PATH), and return None/unknown for an unreadable object, never "absent" (absent would warn falsely).

**Why:** a hook must not wait on the network, and a skipped unreadable blob reads as a missing heading.
**How to apply:** test it with a `--filter=blob:none --no-checkout` clone checked out behind the remote, counting fetch children via GIT_TRACE (`run_command` + ` fetch`), with a positive control that plain git starts one. Mutations: drop env; skip the blob instead of returning None. See [[merge-target-hook-reads-origin-ref-too]].

*References: merge-target-hook-reads-origin-ref-too*

*Observed 2026-11-12 (python-dev)*

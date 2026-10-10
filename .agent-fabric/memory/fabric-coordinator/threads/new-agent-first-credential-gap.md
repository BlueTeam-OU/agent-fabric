---
role: "fabric-coordinator"
class: threads
topic: "new-agent-first-credential-gap"
description: "A brand-new account's first credential path is the parent's enrolment bundle, not a push by the child"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 010ee174dba6c3e3
  - 4be0aca289fb080e
---

## A brand-new account's first credential path is the parent's enrolment bundle, not a push by the child

A new account has no GitHub credential until its first `fabric-secrets sync`, so the child cannot push its own store first. The path (ADR-042 amendment 2026-10-04, "first contact through the enrolment bundle") is the parent's: the parent creates and pushes the store, hands the child a git bundle (`store seed-child`), and the child applies it (`take-bundle`) and runs `sync --no-pull` before the keys PR merges (tools/fabric/new_agent.py; tools/fabric/secretstore/mirrors.py; tests/test_first_contact.py). `runtime/provisioning/new-agent.sh` is a shim onto it, and every step is idempotent: resume with the same command after a failure.

A failed git push of a store reports the line that says what failed ("fatal:", the server's "ERROR:"), not git's trailing "hint:" advice (`_failure`, tools/fabric/secretstore/core.py).

*Observed 2026-10-10 (fabric-coordinator)*

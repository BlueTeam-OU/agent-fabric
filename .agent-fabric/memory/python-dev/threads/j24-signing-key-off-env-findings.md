---
role: "python-dev"
class: threads
topic: "j24-signing-key-off-env-findings"
description: j24 (signing key off the environment; agentd memory sampling) — what was built, on which branch, and what is left for the coordinator
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1fe59712bbc824c1
  - d19bbfa6a47264f5
---

## j24 (signing key off the environment; agentd memory sampling) — what was built, on which branch, and what is left for the coordinator

Built and on main (2026-10-04, commits 70c92e8 and 9a24780): the control-plane signing key is off the environment —
`FABRIC_CONTROL_SIGNING_KEY` is a store-only name (secrets_sync STORE_ONLY: never exported to secrets.env, kept in
`known`), and signing decrypts it from the operator's store (`signing_key()` in tools/fabric/control/ctl.py, once
`signingKey()` of ctl.mjs); agentd samples its own account's memory into a ring (pressure, host op `memory_pressure`,
`memory:` line of ctl host).

State now: `fabric-ctl keygen` no longer points at a sync — it says "next: commit the registry change; the fleet trusts it
once it has pulled that commit". The `agent_env.FABRIC_CONTROL_SIGNING_KEY` entry in projects/registry.json still exists as
the description of the name (only the operator's own store carries it); whether it should stay, and whether a running shell
keeps an exported value until its next sync and relaunch, are the coordinator's and not checked since.

Lessons that outlive the job:
- A fake relay's long `/api/wait` loop can outlive `r.close()` (a resident daemon's 55 s wait added 55 s to the suite):
  end it on `req.socket.destroyed`.
- A read that failed (EACCES, ENOTDIR) is not bad content: replacing a ring or a file after a failed read destroys what a
  later reader could have used; a test caught it.
- A secret that must never reach an environment needs its own list (STORE_ONLY) and a test with a valid other key in the
  environment on every run, or a stray export passes for the right one.

*Observed 2026-10-10 (python-dev)*

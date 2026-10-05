---
role: "python-dev"
class: threads
topic: "j24-signing-key-off-env-findings"
description: j24 (signing key off the environment; agentd memory sampling) — what was built, on which branch, and what is left for the coordinator
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d19bbfa6a47264f5
---

## j24 (signing key off the environment; agentd memory sampling) — what was built, on which branch, and what is left for the coordinator

Request: coordinator's REQUEST 01a10837-9c92-7269-8195-47e9cfb557d7
(2026-10-04). Branch develop-qzapp/python-dev-01/for/user/mods-and-signing-key,
worktree ~/projects/agent-fabric-mods-and-signing-key, off origin/main 7495c69.

Built (2026-10-04):
- 70c92e8 item 1: secrets_sync STORE_ONLY = [FABRIC_CONTROL_SIGNING_KEY]
  (never exported, kept in `known`); ctl.mjs signingKey() runs gpg
  --decrypt on <store>/env/<NAME>.gpg itself (secret_store.py promises no
  function prints a value, so no `store get`), each failure its own line.
  Tests: operatorStore() fixture in ctl.test.mjs (scratch GNUPGHOME + real
  encrypted entry, gpgconf --kill in finally); a valid other key in env on
  every run.
- 9a24780 item 2: runtime/control/pressure.mjs; ring
  <stateDir>/memory-pressure.json, 1440 samples; host op `memory_pressure`;
  ctl host `memory:` line. Reading of "own account only": each daemon its
  own state, no other account's read.
- Learnt: the agentd.test fake relay's /api/wait loop outlived r.close()
  for a resident daemon's 55 s wait (suite +55 s); fixed with
  req.socket.destroyed. A read that failed (EACCES/ENOTDIR) must not be
  treated as bad content — a test caught the ring being replaced.

Left for the coordinator (theirs): projects/registry.json top-level
agent_env entry for FABRIC_CONTROL_SIGNING_KEY is now dead text; running
shells keep the exported value until the next sync + relaunch; keygen's
"next: bin/fabric-secrets sync" line no longer needed for the key (keygen
left unchanged as asked).

*Observed 2026-10-04 (python-dev)*

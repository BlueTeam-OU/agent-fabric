---
role: shared
class: solution
topic: "gnupghome-default-agent-trap"
description: "A test GNUPGHOME equal to $HOME/.gnupg shares the account's REAL gpg-agent — scratch keys land in ~/.gnupg and \"separate\" keyrings decrypt each other"
tier: 2
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
  - 2cff70ffd71bab39
---

## A test GNUPGHOME equal to $HOME/.gnupg shares the account's REAL gpg-agent — scratch keys land in ~/.gnupg and "separate" keyrings decrypt each other

This happened on 2026-09-29 while building `tools/fabric/secret_store.py` (agent-fabric ADR-038). The test gave each scratch role `HOME=<tmp>/x` and `GNUPGHOME=<tmp>/x/.gnupg`. gpg treats a GNUPGHOME equal to `$HOME/.gnupg` as the DEFAULT home, so it uses the per-user default socket `/run/user/<uid>/gnupg/S.gpg-agent`: the running account's real agent. Two consequences followed:
- the scratch "parent" decrypted the scratch "child's" entry;
- twelve test private keys were written into the real `~/.gnupg/private-keys-v1.d`.

They were found by date, proved orphans (none of the real keyring's keygrips), and removed with `gpg-connect-agent "DELETE_KEY --force <grip>"`.

**Why:** gpg's agent isolation is by socket, and a "separate" keyring that shares the default socket is not separate. Production is safe only because each agent is its own Unix user, with per-uid agents.

**How to apply:**
- In any gpg test, put each keyring outside its scratch HOME (for example `<tmp>/<role>-gnupg`).
- Assert that `gpgconf --list-dirs agent-socket` differs per role and from the default socket.
- Snapshot the real `~/.gnupg/private-keys-v1.d` before the run and compare it after.
- Kill each scratch agent with `gpgconf --homedir X --kill all`.

See `tests/test_secret_store.py` and [[suite-scratch-leak]].

*References: suite-scratch-leak*

*Observed 2026-09-29 (fabric-coordinator)*

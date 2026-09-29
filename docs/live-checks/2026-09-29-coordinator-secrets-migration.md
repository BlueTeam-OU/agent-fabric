# 2026-09-29 — The coordinator moves its secrets to its own store

The first real run of ADR-038's path, on develop-qzapp as `user`, the
fabric-coordinator login and the root of the key chain, after #63
merged (e00f750) and was distributed to every account.

## Enrolment

`runtime/provisioning/secrets/store-enroll.sh --self` did the following:
- It created the private repository `gzapi-org/secrets-user`; GitHub
  reports its visibility as `PRIVATE`.
- It made the account's key in its own keyring,
  `F15AA499C738645876F73030E6BDB76C59372015`, a primary key plus an
  encryption subkey. Two new private-key files appeared, and their
  keygrips are exactly that key's.
- It initialised the store and pushed it over SSH. That settles the
  reviewer's question on #63: an account's SSH key can write to its own
  private secrets repository.
- It recorded the key in `identities/keys/` as the root, with no parent.

`fabric-secrets store verify` and lint are both clean.

## The first migration stopped, safely

`fabric-ctl user secrets-migrate` failed at its baseline sync from
Doppler, with an empty reason. The account's source was never touched.

- **The cause,** from `/proc/<pid>/fd` and `ss -xap` (strace is not
  installed): the only socket of `doppler configure get enclave.config`
  was `/run/user/1000/bus`. The coordinator's Doppler token is kept in
  the desktop keyring: its `.doppler.yaml` entry is a keyring pointer.
  That keyring was locked, so every doppler call waited forever. Hiding
  `DBUS_SESSION_BUS_ADDRESS` does not help, because the library falls
  back to the default bus path.
- **Two defects it exposed,** both fixed on the rollout branch (cd44785):
  - `fabric-secrets` fell back to `agents_user` after the hung lookup,
    while the recorded config is `agents2_user`;
  - a call killed by its timeout reported no reason.

  Every doppler call is now bounded. A failed or hung lookup stops the
  sync with its reason, and the migration names a timeout.

## The migration

The owner unlocked the keyring, and `doppler configure get` then
answered at once. `fabric-ctl user secrets-migrate` then returned:

```
user   migrated   bafc7e494d75
```

That is Doppler's `values_sha256`, the store's before the switch, and
the sync's after it, all equal. Read back afterwards:

- **The source:** `~/.config/agent-fabric/secrets-source` holds `store`.
- **`fabric-secrets sync --json`:**
  - it reads the store;
  - `missing` is empty;
  - `values_sha256` is `bafc7e494d75…`;
  - there is no error.
- **The store:** 18 entries, level with `origin/main`.
- **The Claude token:** `fabric-status` still reads it, as
  `setup-token 183a68e97389`, the same fingerprint as before.

## What it decides

The migration path works on a real account. The fleet follows the same
two steps:
1. `store-enroll.sh <login>`, which this coordinator runs as the parent;
2. `fabric-ctl <login> secrets-migrate`.

One condition from this run applies to the coordinator only: while it
still reads Doppler, the keyring holding its token must be unlocked.
The other accounts hold read-only service tokens in their own config
files and do not depend on it.

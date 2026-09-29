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

## The recovery key (option B)

The owner's first `store recovery-key init` wrote a public half, but no
private half reached Proton. gpg's pinentry had asked for the passphrase
out of the owner's sight, and the private half went with the throwaway
keyring. The second run failed at Proton, because `list` output was read
as paths. Both were fixed (6acfe27, 6ccbb00): the passphrase is now asked
on the terminal, protection is checked through KEYINFO, and the public
half is written only after the upload.

The third run made `40A7633D78102CB8FA3F1CAB19A371CA986E3820`. Read back:

- **Proton `keys/`** holds `recovery-key.asc` (898 B) and
  `user.key.gpg`. The coordinator's copy has a single pubkey-encrypted
  packet, to the recovery subkey `82C53CF305BAC51D`.
- **`backup --verify`** reports that every bundle matches its manifest.
- **The coordinator's store** is level with its remote.
- **The plain `user.key.txt`** was trashed and then deleted. `keys/` and
  the trash no longer list it.

## The agent id (ADR-039)

The coordinator's id was minted from its home's creation time,
`2026-01-14 21:27:33.247294044 +0100`:
`019bbe31-2fff-7a2f-9849-96bdf286e011`, born `2026-01-14T20:27:33.247Z`.

**First design: the id everywhere.** The first version named everything
by the id: the repository, the key file, the lineage key and the Proton
files. The owner read it and asked for names wherever a person reads
them, with the id underneath. The coordinator was moved twice. The final
state, read back:

- **Repository:** `gzapi-org/agent-fabric-secrets-user`, private, its
  description naming the agent id. It was renamed from `secrets-user`,
  through the id-named form and back.
- **Lineage:** `lineage.json` has one entry, `user`, with `agent_id`,
  `born`, `fingerprint` and a null parent. The key file is
  `identities/keys/user.asc`, and `verify` is clean.
- **Key:** the same key, `F15AA499…2015`. It gained the user id
  `user <019bbe31-…@agents.agent-fabric>`. The account still has 4
  private-key files.
- **Store:** it holds `.agent-id` and `recovery/user.key.gpg`, and is
  level with its remote.
- **Proton:** `secrets/agent-fabric-secrets-user.bundle` (`--verify`
  matches), `keys/user.key.gpg` and `keys/recovery-key.asc`. Every other
  file there was trashed and then deleted.

**Two defects, found on the way, both fixed with the test that catches
them:**

1. `store-enroll.sh` read `lineage.json` from its own checkout, not from
   the fabric root the store tool certifies into. On the enrolment
   test's second run it minted a fresh id, and `init` refused it. The
   lookup is now the store tool's `id-of`.
2. A rewrite of the recovery sheet turned its last line into a plain
   string. The copy then carried `{sheet}` and `{revocation}` literally:
   412 bytes instead of 1,909. The test had checked for "REVOCATION",
   which the literal matched once uppercased. It now checks for
   paperkey's header and the armored revocation block. With only that
   bug put back, the test fails. The copy was re-made at 1,909 bytes.
   The earlier complete copies stay in the store's history.

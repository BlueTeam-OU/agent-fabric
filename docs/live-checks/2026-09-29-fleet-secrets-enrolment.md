# 2026-09-29 — The fleet moves to its own stores

The other 15 accounts on develop-qzapp were enrolled into ADR-038 stores,
the day the coordinator was, after #65 merged (ff8d14f). #65 is the
one-key-per-use layout. Every account was upgraded to ff8d14f first,
because an older checkout answers `store id` without the exit 3 that
enrolment needs.

## How

**The trial: flutter-dev-02, which had no session running.**
1. A dry run of `store-enroll.sh`.
2. The minted id's time was compared with the account's home creation
   time, read on its host: `2026-08-16 20:06:51.338 +0200` against
   `2026-08-16T18:06:51.338Z`, equal to the millisecond.
3. The enrolment itself.
4. `fabric-ctl flutter-dev-02 secrets-migrate`, then the account's
   `store recovery-copy`.
5. Read back: the source is `store`; sync reads it with nothing missing;
   SSH to GitHub authenticates; `fabric-status` reads the same Claude
   setup-token.

**The other 14,** one at a time: enrol, migrate, then the recovery copy.
The loop was set to stop at the first failure, and none failed. Each
migration compared Doppler's `values_sha256` with the store's before it
switched, and with the new sync's after.

## Read back

- `identities/keys/lineage.json`: 16 entries, one root (the
  coordinator), every other agent certified by it. `verify` and lint are
  clean, including each key's encryption, signing and authentication
  subkeys.
- Every id's time is its home's creation time.
  - Nine accounts made together by provisioning were born within 300 ms
    of each other on 2026-08-16.
  - architect-cto-01 was born 2026-08-13.
  - The language and communication accounts were born 15–18 September.
- As each of the 16 accounts:
  - the source is `store`;
  - `fabric-secrets sync` reads the store with nothing missing and no
    error;
  - `ssh -T git@github.com` authenticates.
- The coordinator's `store backup` uploaded 16 bundles and 16 recovery
  copies. `backup --verify` finds every bundle and every recovery copy
  matching its manifest.
- Running sessions were not disturbed: their `secrets.env` is the same
  file, by hash.

## What it decides

Doppler now serves no account's `secrets.env`. What remains of it is
the reader, the enrolment script, the binary and each account's read
token, which is PR B (ADR-038 §7). Deleting the Doppler project is the
owner's own act.

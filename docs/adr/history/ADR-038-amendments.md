# ADR-038 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-29 — The recovery copy and the backup go to Proton Drive

The owner chose not to print the per-agent sheets: "you will simply
access proton drive via cli and save that there". Each key's recovery
copy, and a bundle of every store, therefore go to a Proton Drive
account dedicated to the fleet. Proton Drive has no app keys, so the
owner's own account never signs in on the agents' host. The trade was
named before it was taken: that account becomes the single recovery
point for every agent, so its 2FA and recovery phrase are what the owner
keeps. It was read back live on the coordinator: a backup, a
`--verify` of that backup against its manifest, and its recovery copy.

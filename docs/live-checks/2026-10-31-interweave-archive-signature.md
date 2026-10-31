# 2026-10-31 — the InterWeave v0.2.0 archive's minisign signature

Run by fabric-coordinator (user@develop-qzapp, job j449) on develop-qzapp. The question: can the pinned v0.2.0 archive be held to the owner's minisign signature, beside the SHA-256 `runtime/interweave/release.json` already pins (agent-fabric ADR-064 §5 rule 4), with what the fleet's pinned Python has? Until now the installer checked the digest alone. v0.2.0 ships a `.minisig` for the archive and for its `.sha256`; v0.1.0 ships neither.

## The key

InterWeave's `packaging/release-keys.toml`, `[archive] minisign_public_key`, read on InterWeave's main at b1b65cb9 ("release-keys: the owner's archive key", 2026-10-27), unchanged on main at the time of this check and identical in the v0.2.0 tag:

    RWThBWgfksKOWwyUdI0RKNXvsbRU5wqjGS3PPQc0oJ6R9rjV1kPoiJs4    key id 5B8EC2921F6805E1

The file says its release job reads the key from main's tip, never from the tag's commit, so main is where the fabric reads it from.

## What was measured

The release's assets, from `gh api repos/BlueTeam-OU/InterWeave/releases/tags/v0.2.0`, downloaded with the asset endpoint:

| asset | id | size | sha256 |
|---|---|---|---|
| `interweave-0.2.0-x86_64-unknown-linux-gnu.tar.gz` | 684207601 | 118515427 | `5fc4cc02…1627cd7`, the pin's |
| `….tar.gz.minisig` | 684207604 | 343 | `cbf72a15…dacf81d43` |
| `….tar.gz.sha256` | 684207603 | 115 | `8c94262c…d7d09f05` |
| `….tar.gz.sha256.minisig` | 684207633 | 350 | `1a42a355…bdc3f485` |

| case | result |
|---|---|
| `minisign -Vm` the archive, its `.minisig`, the pinned key | verified; trusted comment `timestamp:1793172713 file:interweave-0.2.0-x86_64-unknown-linux-gnu.tar.gz hashed` |
| `minisign -Vm` the `.sha256`, its `.minisig`, the pinned key | verified; its line names the archive's pinned digest |
| control: the archive with one byte changed | `Signature verification failed`, exit 1 |
| control: a freshly generated other key | refused, "key id … is 5B8EC2921F6805E1 but the key id in the public key is 7E00CE2A040FAEE9", exit 1 |
| the `.minisig` rebuilt from `release.json` alone, `minisign -Vm` | verified |
| the same, by a verifier using only the standard library (BLAKE2b-512 and RFC 8032 §5.1.7 Ed25519 verification) | archive and trusted-comment signature both verified; a changed byte and an edited trusted comment both refused |

The signature is minisign's prehashed kind (`ED`): Ed25519 over the archive's BLAKE2b-512 digest, and a second Ed25519 signature over the first signature and the trusted comment. `hashlib.blake2b` is in fabric-python 3.14.9; `cryptography` is not, and the `minisign` program is installed on this host but provisioned on none, so the installer's check has to be the standard-library one.

## What it decides

The v0.2.0 archive is signed by the key InterWeave pins, and that signature can be checked by the installer with nothing added to the hosts. `release.json` now pins the key per release, with the InterWeave commit it was read from, and the signature itself (its three lines), so nothing about the signature is fetched at install time; v0.1.0 is marked `unsigned`.

## Not verified

- The installer's check itself: it is python-dev's to build (agent-fabric ADR-064, amendment 2026-10-31), and this page is its oracle.
- The tag key (`[tag]`, an OpenPGP key): the tag's signature is InterWeave's release job's check, not the archive's, and the fabric does not install from a tag.
- A key rotation: only one archive key has existed.

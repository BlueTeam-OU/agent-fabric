# 2026-10-09: can the Python control plane sign and verify Ed25519 through the host's openssl?

**Why.** The owner moved the control plane to Python (ADR-040, Wave 8). Every action it answers is signed with the operator's Ed25519 key (ADR-029 rule 5), and Python's standard library has no Ed25519. ADR-040 allows the standard library only. The host's `openssl` is the candidate.

**Measured on develop-qzapp, 2026-10-09, OpenSSL 3.5.8:**
- `openssl genpkey -algorithm ed25519` made a key; `openssl pkeyutl -sign -rawin` signed a five-byte message, and `openssl pkeyutl -verify -pubin -rawin` verified it.
- Node's `crypto.verify(null, …)` accepted the openssl signature with the same PEM public key.
- Node's `crypto.sign(null, …)` with the same private key produced the same 64 signature bytes. Ed25519 is deterministic, so the primitive agrees: the same key over the same bytes gives the same signature. That is all this check shows.

**Not measured.**
- The bytes that are signed. sign.mjs signs `canonical(rest)`, built with `JSON.stringify`; Python's `json.dumps` differs by default (it escapes non-ASCII, writes `5.0` where Node writes `5`, and puts spaces after separators). A Python signer must reproduce Node's serialisation exactly, non-ASCII strings and numbers included, or a Node agent refuses every action it signs.
- The key formats: the private key's store form (`ed25519-pkcs8:<base64>`) and the public key's (`ed25519:` + SPKI DER in base64, as `runtime/hosts/registry.json` holds it), each converted to what `openssl pkeyutl` reads, and back.
- How the key reaches openssl. A pipe and a file of mode 0600 are the two candidates; the second writes the decrypted signing key to disk. Neither was tried.
- The openssl version on every placed host and in CI's images (Debian and Fedora); it is not yet part of the host contract that provisioning installs and audits.
- The cost of one process per signature on a fleet-wide action.

**What it decides.** The Python control plane signs and verifies through `openssl pkeyutl -rawin`, a key never on a command line. Everything under "Not measured" is Wave 8's first check, before any cutover; the key path is chosen by that check.

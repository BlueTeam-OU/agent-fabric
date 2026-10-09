# 2026-10-09: can the Python control plane sign and verify Ed25519 through the host's openssl?

**Why.** The owner moved the control plane to Python (ADR-040, Wave 8). Every action it answers is signed with the operator's Ed25519 key (ADR-029 rule 5), and Python's standard library has no Ed25519. ADR-040 allows the standard library only. The host's `openssl` is the candidate.

**Measured on develop-qzapp, 2026-10-09, OpenSSL 3.5.8:**
- `openssl genpkey -algorithm ed25519` made a key; `openssl pkeyutl -sign -rawin` signed a five-byte message, and `openssl pkeyutl -verify -pubin -rawin` verified it.
- Node's `crypto.verify(null, …)` accepted the openssl signature with the same PEM public key.
- Node's `crypto.sign(null, …)` with the same private key produced the same 64 signature bytes. Ed25519 is deterministic, so the two implementations are interchangeable on the wire.

**Not measured.** The signing key's store format (`ed25519-pkcs8:<base64>`, runtime/control/sign.mjs) converted to and from PEM; the openssl version on every placed host and in CI's images (Debian and Fedora); the cost of one process per signature on a fleet-wide action.

**What it decides.** The Python control plane signs and verifies through `openssl pkeyutl -rawin`, a key never on a command line (a file of mode 0600, or a pipe). The three unmeasured points are Wave 8's first checks, before any cutover.

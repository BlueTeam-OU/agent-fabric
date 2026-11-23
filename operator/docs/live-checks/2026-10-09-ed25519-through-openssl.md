# 2026-10-09: can the Python control plane sign and verify Ed25519 through the host's openssl?

**Why.** The owner moved the control plane to Python (ADR-040, Wave 8). Every action it answers is signed with the operator's Ed25519 key (ADR-029 rule 5), and Python's standard library has no Ed25519. ADR-040 allows the standard library only. The host's `openssl` is the candidate.

**Measured on develop-qzapp, 2026-10-09, OpenSSL 3.5.8:**
- `openssl genpkey -algorithm ed25519` made a key; `openssl pkeyutl -sign -rawin` signed a five-byte message, and `openssl pkeyutl -verify -pubin -rawin` verified it.
- Node's `crypto.verify(null, …)` accepted the openssl signature with the same PEM public key.
- Node's `crypto.sign(null, …)` with the same private key produced the same 64 signature bytes. Ed25519 is deterministic, so the primitive agrees: the same key over the same bytes gives the same signature. That is all this check shows.

**Not measured.**
- The bytes that are signed. sign.mjs signs `canonical(rest)`, built with `JSON.stringify`; Python's `json.dumps` differs by default (it escapes non-ASCII, writes `5.0` where Node writes `5`, and puts spaces after separators). A Python signer must reproduce Node's serialisation exactly, non-ASCII strings and numbers included, or a Node agent refuses every action it signs.

**Measured after (python-dev-01, 2026-10-09):**
- Key formats. The store's `ed25519-pkcs8:<base64>` is PKCS#8 DER (48 bytes) and `ed25519:<base64>` is SPKI DER (44); `openssl pkeyutl` reads both as `-keyform DER`, with no PEM step. Back: an `openssl genpkey -outform DER` key, and its `pkey -pubout -outform DER`, put in the two store forms, are read by sign.mjs `privateKeyFrom` / `publicKeyFrom`, and `signRequest` / `verifyRequest` round-trip with them.
- Key path. The private key goes through a pipe the child reads as `-inkey /dev/fd/N` (`pass_fds`), never a file, never argv: openssl signed from it, the 64 bytes were identical to Node `crypto.sign` with the same key over the same bytes, and Node verified them. openssl verified Node's signature with the SPKI DER key and the signature both from pipes; a one-bit change to the message was refused (the control).
- The message cannot come through a pipe or stdin: Ed25519 is one-shot, and openssl refuses "unable to determine file size for oneshot operation" (3.0.13 and 3.5.8 alike). The signed bytes are public, so they go in a 0600 file in a private temporary directory, removed after the call.
- Versions. develop-qzapp, the one host `runtime/hosts/registry.json` places: 3.5.8. CI's container images ship no openssl binary: debian:stable-slim (13), fedora:latest (44) and ubuntu:24.04 all lack it. Installed from their own repositories: 3.5.7, 3.5.9 and 3.0.13, and each signs and verifies Ed25519 `-rawin` from DER. ubuntu-latest (the runner, not a container) not measured.
- Cost, one process per call, on develop-qzapp: sign 9.1 ms, verify 6.8 ms (mean of 200 each, the key through a pipe and the message through a file).
- What follows for the host contract: openssl is installed, not assumed, in every image and host provisioning makes; 3.0 is the lowest measured.

**What it decides.** The Python control plane signs and verifies through `openssl pkeyutl -rawin`, a key never on a command line. The key reaches openssl through a pipe (`/dev/fd/N`), never a file; the signed bytes, which are public, through a private 0600 file. The bytes signed, still under "Not measured", are the serialiser's own suite, before any cutover.

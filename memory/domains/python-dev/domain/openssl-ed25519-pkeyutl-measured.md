---
role: "python-dev"
class: domain
topic: "openssl-ed25519-pkeyutl-measured"
description: "openssl pkeyutl Ed25519 from Python — key via /dev/fd pipe works, message must be a regular file (one-shot), DER store forms read directly; CI images lack openssl; ~9 ms/sign"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a0377b82feba867e
---

## openssl pkeyutl Ed25519 from Python — key via /dev/fd pipe works, message must be a regular file (one-shot), DER store forms read directly; CI images lack openssl; ~9 ms/sign

Measured 2026-10-09 (OpenSSL 3.0.13, 3.5.7, 3.5.8, 3.5.9), for Wave 8's sign.py:
- `openssl pkeyutl -sign -rawin -keyform DER -inkey /dev/fd/N -in <file>`: key DER through an os.pipe passed with
  subprocess pass_fds works (never argv, never disk). Signature identical to Node crypto.sign; Node verifies it.
- The MESSAGE cannot be a pipe or stdin: "unable to determine file size for oneshot operation". Use a 0600 file in a
  private TemporaryDirectory (the signed bytes are public). -sigfile and a -pubin key CAN come from pipes.
- Every extra pipe fd must be in pass_fds, or the child cannot open /dev/fd/N (my first verify "failed" for that reason).
- Store forms: ed25519-pkcs8:<b64> = PKCS#8 DER (48 B), ed25519:<b64> = SPKI DER (44 B): -keyform DER, no PEM.
- debian:stable-slim, fedora:latest, ubuntu:24.04 images ship NO openssl binary; installed it is 3.5.7 / 3.5.9 / 3.0.13.
- Cost: sign 9.1 ms, verify 6.8 ms per process on develop-qzapp.
Sent to fabric-coordinator as REPLY 01a11e7c-380a-7808-9010-1bb92ee7481f for the live-check note.
**Why:** sign.py's subprocess design follows from these; a wrong guess (message on stdin) fails every signature.
**How to apply:** key by pipe + pass_fds, message by 0600 temp file, check returncode, timeout. Related: [[wave-8-signed-bytes-and-frozen-state]].

*References: wave-8-signed-bytes-and-frozen-state*

*Observed 2026-10-09 (python-dev)*

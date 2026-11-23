# GitHub's SSH host keys, read back — 2026-09-16

**What was read back.** `https://api.github.com/meta` (`ssh_keys` and
`ssh_key_fingerprints`), over HTTPS, from this host, at 2026-09-16; the
three keys written to `runtime/provisioning/github-host-keys` in
known_hosts format and their fingerprints computed locally with
`ssh-keygen -lf`.

**Findings.**

1. The API returned three keys: ED25519, ECDSA (nistp256), RSA (3072).
2. `ssh-keygen -lf` on the committed file gives
   `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU` (ED25519),
   `SHA256:p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM` (ECDSA),
   `SHA256:uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s` (RSA) — the
   same three the API's `ssh_key_fingerprints` names, and the three
   GitHub publishes on docs.github.com ("GitHub's SSH key fingerprints").
   Two independent channels (the API over TLS, the documentation) agree
   with the file, which is what a scan of the host on the network being
   bootstrapped could never give.
3. The fingerprints are committed beside the file
   (`github-host-keys.fingerprints`); `tests/static.sh` recomputes them
   from the key file on every run and refuses a mismatch, and refuses
   `ssh-keyscan` anywhere under `runtime/provisioning/`.

**What this decides.** Provisioning installs GitHub's host keys from the
committed published set (`new-agent.sh` step 3), never from
`ssh-keyscan`. A key rotation at GitHub is a change to the committed file
and its fingerprint list, reviewed against docs.github.com like any
other change. A host that already holds one of the lines gets only the
missing ones appended.

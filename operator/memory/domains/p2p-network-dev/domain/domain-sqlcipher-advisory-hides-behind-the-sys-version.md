---
role: "p2p-network-dev"
class: domain
topic: "domain-sqlcipher-advisory-hides-behind-the-sys-version"
description: "a bundled-sqlcipher build takes its SQLite from sqlcipher-src, so a libsqlite3-sys bump that clears a RustSec SQLite advisory can leave the shipped SQLite affected"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 5ffe43edd5774c5d
---

## a bundled-sqlcipher build takes its SQLite from sqlcipher-src, so a libsqlite3-sys bump that clears a RustSec SQLite advisory can leave the shipped SQLite affected

RUSTSEC-2026-0459 (SQLite < 3.54.0) lists libsqlite3-sys >= 0.39.0 as patched, so cargo-deny clears on the bump. But with `bundled-sqlcipher*` the C source is `sqlcipher-src`, and libsqlite3-sys 0.39.1 pins it `=419.0.6` (SQLite 3.53.4, affected), while sqlcipher-src 420.0.0 (SQLite 3.54.1) sits out of reach of `cargo update`. The scanner judges the -sys crate's version, not the SQLite inside it: the same blind spot as a vendored crate.

**How to apply:** for any SQLite advisory, read the lock's `sqlcipher-src` version string (it names the SQLite) and the -sys crate's exact pin (download the .crate and read its manifest), not only the deny result. Found 2026-11-09 on devex-tooling's j306 branch (58f4df7a3); OBSERVATION 01a1c039 sent to devex-tooling.
devex-tooling already knew (58f4df7a3 msg); architect-cto-01 ruled no vendoring/no hold (-wal writer outside ADR-0060's threat model, INFO 01a1c023); residual + re-check trigger (libsqlite3-sys on sqlcipher-src >=420) in their PR body; plaintext-rewrite/restore path raised as open question to architect-cto-01 (REPLY 01a1c039-f62e).
12:38Z architect-cto-01 DECISION 01a1c051: ruling covers every store open path (all in the private human dir, at_rest.rs 154-159/557/647; no restore/import path); no added condition; recorded in #601. Thread CLOSED.

*Observed 2026-11-09 (p2p-network-dev)*

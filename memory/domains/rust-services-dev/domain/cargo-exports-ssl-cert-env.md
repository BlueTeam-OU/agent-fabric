---
role: "rust-services-dev"
class: domain
topic: "cargo-exports-ssl-cert-env"
description: "cargo sets SSL_CERT_FILE/SSL_CERT_DIR for every child; rustls-native-certs then reads them instead of the host store"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - 2071d05ae208533c
---

## cargo sets SSL_CERT_FILE/SSL_CERT_DIR for every child; rustls-native-certs then reads them instead of the host store

cargo (it links OpenSSL and runs openssl-probe's env init) exports SSL_CERT_FILE and
SSL_CERT_DIR to every process it starts — rustc, `cargo test` binaries, `cargo run` —
even when the login shell has neither (seen 2026-10-08 on Fedora: the host bundle and
/etc/pki/tls/certs). rustls_native_certs::load_native_certs() (0.8) reads those
variables *instead of* the platform store when set, and openssl_probe::probe() honours
them too. So "refuse to start if set" breaks every test under cargo, and "load_native_certs"
lets the environment choose the trust. Env-free host store: openssl_probe::candidate_cert_dirs()
fed to rustls_native_certs::load_certs_from_paths(None, Some(dir)).
To test env-independence without set_var (unsafe, denied): re-run the test binary
(std::env::current_exe) as a child with the variables set, on an #[ignore]d child test.

Gateway use: crates/backend/http/src/trust.rs, PR #11 (j4); decision on ignoring the
variables asked of fabric-coordinator in GZCoord 01a11bf2-6211-7818-ba0d-0bd5a7e8407f.

*Observed 2026-10-08 (rust-services-dev)*

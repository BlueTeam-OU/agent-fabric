---
role: "rust-services-dev"
class: index
description: "What rust-services-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-12"
---

# rust-services-dev — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/rust-services-dev/charter.md`](identities/roles/rust-services-dev/charter.md) — The fleet's network-services developer in Rust: proxies, gateways and API servers — streaming, cancellation, retry and failover, TLS and credential boundaries — proven over real sockets.

## brief

- [`identities/roles/rust-services-dev/brief.md`](identities/roles/rust-services-dev/brief.md) — How rust-services-dev works day to day, in any project: the service boundary written as a contract first, a failure matrix before done, wire behaviour proved over real sockets, and credentials kept inside the process.

## domain

- [`memory/domains/rust-services-dev/domain/cargo-exports-ssl-cert-env.md`](memory/domains/rust-services-dev/domain/cargo-exports-ssl-cert-env.md) — cargo sets SSL_CERT_FILE/SSL_CERT_DIR for every child; rustls-native-certs then reads them instead of the host store
- [`memory/domains/rust-services-dev/domain/cargo-machete-silent-pass.md`](memory/domains/rust-services-dev/domain/cargo-machete-silent-pass.md) — cargo-machete 0.9.2 default mode skips dev-deps; --with-metadata reports unreadable crates clean with exit 0
- [`memory/domains/rust-services-dev/domain/hyper-cancellation-and-head-deadline.md`](memory/domains/rust-services-dev/domain/hyper-cancellation-and-head-deadline.md) — What hyper 1.x itself does on body drop and idle connections, and how gateway tests separate it from the gateway's own guards
- [`memory/domains/rust-services-dev/domain/hyper-client-closes-finished-sized-body.md`](memory/domains/rust-services-dev/domain/hyper-client-closes-finished-sized-body.md) — A test proving the gateway closed an upstream connection must leave that response's body unfinished — hyper's client closes a fully-received sized body itself
- [`memory/domains/rust-services-dev/domain/nofollow-directory-symlink-enotdir.md`](memory/domains/rust-services-dev/domain/nofollow-directory-symlink-enotdir.md) — openat(O_DIRECTORY|O_NOFOLLOW) on a symlink fails ENOTDIR on Linux, not ELOOP; classify with fstatat
- [`memory/domains/rust-services-dev/domain/serde-derive-accepts-arrays.md`](memory/domains/rust-services-dev/domain/serde-derive-accepts-arrays.md) — A derived serde struct also deserializes from a JSON array; a field probe that must only accept objects needs a map-only visitor
- [`memory/domains/rust-services-dev/domain/serde-tagged-unit-variant-ignores-unknown.md`](memory/domains/rust-services-dev/domain/serde-tagged-unit-variant-ignores-unknown.md) — serde internally tagged enum unit variant accepts unknown keys despite deny_unknown_fields; use an empty struct variant
- [`memory/domains/rust-services-dev/domain/tracing-set-default-misses-events.md`](memory/domains/rust-services-dev/domain/tracing-set-default-misses-events.md) — a thread-scoped tracing subscriber in a unit test misses events when other tests hit the same callsite; log tests need their own binary

## threads

- [`.agent-fabric/memory/rust-services-dev/threads.md`](.agent-fabric/memory/rust-services-dev/threads.md) — Gateway Stage 6 — who does steps 4-7, the agreed API of gateway-protocol-openai-responses, and the usage-op contract decision

## recall

- [`identities/roles/rust-services-dev/recall.md`](identities/roles/rust-services-dev/recall.md) — Where rust-services-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.

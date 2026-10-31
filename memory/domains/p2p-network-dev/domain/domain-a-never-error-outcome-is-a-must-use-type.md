---
role: "p2p-network-dev"
class: domain
topic: "domain-a-never-error-outcome-is-a-must-use-type"
description: "Rust port API: when a call that returned Result<(), E> gains an outcome that is 'an answer, never an error', return a #[must_use] typed outcome so every `?;` caller fails the build until it handles it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - e511ae6b33b31e9b
---

## Rust port API: when a call that returned Result<(), E> gains an outcome that is 'an answer, never an error', return a #[must_use] typed outcome so every `?;` caller fails the build until it handles it

`AdminPort::set_trust` returned `Result<(), TransportError>`. A superseded set must not be shown as made. Every
caller wrote `port.set_trust(..).await?;`, which would still compile and silently treat the refusal as success.
architect-cto ruled (REPLY 01a166fe): the return is `Result<TrustChange { Set, Refused(..) }, _>` with
`#[must_use]` on the TYPE. An answer that is never an error must not travel as an Err in Rust either. And the
build failing until each caller handles it is the point.

It worked as intended. `clippy -D warnings` (`unused_must_use`) found every discarding site, including one
nobody listed (tests/android-e2e-cases pairing.rs, in my lane, found by the supplier's build). So the supply was
complete by construction, not by a grep.

Two follow-ons:
- Put `#[must_use]` on the type, not also on each fn that returns it. clippy 1.99's `double_must_use` rejects a
  bare `#[must_use]` on a fn whose return type is already must_use (4 sites at the 1.99.1 bump, 01a16e58).
- A port method that answers a refusal must say so in its docs. A binding returning an error its port contract
  does not name is a finding (01a16688).

**How to apply:** when a contract adds a non-error outcome to a unit-returning call, change the Ok type. Do not
add an error code. Ask each caller's owner for the supply with the commit that changes the return, and run the
workspace clippy on the folded result.

*Observed 2026-10-25 (p2p-network-dev)*

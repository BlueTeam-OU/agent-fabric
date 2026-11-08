---
role: "rust-services-dev"
class: domain
topic: "dependency-diff-check-feature-gate"
description: "before claiming a dependency release changes behaviour, check the hunk's cfg(feature) and follow it to what the caller observes"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - 19ad1e358fca7704
---

## before claiming a dependency release changes behaviour, check the hunk's cfg(feature) and follow it to what the caller observes

While reading serde_json's 1.0.151 -> 1.0.154 source diff (2026-11-04, gateway job j57), I wrote that a bare "-0"
now parses as a float. The commit message said so. But the changed line is in `parse_any_number` under
`#[cfg(feature = "arbitrary_precision")]`, and the gateway's graph enables only default, std and raw_value
(`cargo tree -e features -i serde_json --all-features`). I ran a two-version probe: both versions parse "-0" as -0.0
and refuse it as u64. The claim was wrong, and I reworded the commit before pushing.

On the same PR the review found a second wrong claim of the same kind (F1, answered in 3dc72d8). I wrote that
rustls-native-certs 0.8.5 "no longer adds the same root several times". That was read off the new per-file dedup.
But 0.8.4 already sorts and deduplicates the returned certs at the end of the load, and the gateway's
`UpstreamTrust::from_roots` deduplicates again. Only re-parsing and the repeated `errors` entries changed.

**Why:** a commit message is read as evidence by the review and by the arming authority. A behaviour change read off
a diff without its cfg is a false claim about the system.

**How to apply:** for each behavioural hunk in a dependency diff, do two things.
- Read the enclosing `cfg` and compare it with `cargo tree -e features -i <crate>`.
- Follow the hunk to what the gateway can observe: the function's return after its own post-processing, and what
  the caller reads from it. Where the claim matters, prove it with a small probe crate built offline
against each version, using the pinned toolchain (`cargo +<channel>`, because there is no rustup default here).

*Observed 2026-11-04 (rust-services-dev)*

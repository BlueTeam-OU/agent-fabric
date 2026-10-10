---
role: "p2p-network-dev"
class: domain
topic: "error-text-matching-pins-the-public-type"
description: "when a dependency's error is unexported and matched by its Display text, pin the text on the TYPE THE CALLER RECEIVES and feed the classifier a real event — the AutoNAT client's public Error wraps DialBackError and displays that, so a…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 3590a5fc1f13ab0c
---

## when a dependency's error is unexported and matched by its Display text, pin the text on the TYPE THE CALLER RECEIVES and feed the classifier a real event — the AutoNAT client's public Error wraps DialBackError and displays that, so a classifier matching the handler's AddressNotReachable text matched nothing and every real failure was silently 'no outcome' (PR #89, found 2026-09-18)

libp2p-autonat 0.15.0 (vendored): the handler's `dial_request::Error::AddressNotReachable` displays "Address is not reachable: {error}", but the client's PUBLIC `Event::result` carries `behaviour::Error { inner: DialBackError }` whose `Display` prints the inner text alone — "server failed to establish a connection" / "dial back stream failed". PR #89's `outcome_of` matched the handler's prefix; the source pin `include_str!`'d the handler file; the unit test fed a `String` of the expected shape. All green; no failure vote ever recorded. Fixed in `develop-qzapp/interweave/fix/autonat-outcome-classification` (`classify_outcome`, `DIAL_BACK_FAILURE_TEXTS`, wire test `crates/transport/libp2p/tests/autonat_outcome_wire.rs`).

**Why:** a text match is a contract with the type that reaches the caller, not with the type that defines the text; a pin against source proves the text exists somewhere, not that it is displayed on the path in use. A test that constructs the input from the expected shape agrees with the code for free — CLAUDE.md §4's "feed the test what the caller actually holds".

**How to apply:** when matching an unexported error by text: (1) trace the Display from the event type the caller receives, through every wrapper, to the string; (2) pin THAT chain against the vendored source (the wrapper's field, its `Display::fmt`, the construction site); (3) produce the error for real in a test over the wire and feed the event to the classifier — a two-Swarm loopback harness with the raw crate is enough and takes under a second. An unclassifiable error is counted, never consumed silently. See [[stage-11-pr84-landed]].

*References: stage-11-pr84-landed*

*Observed 2026-09-18 (p2p-network-dev)*

---
role: "rust-services-dev"
class: workflow
topic: "operator-reason-labels-are-contract"
description: "A drop or refusal counter's reason labels are a closed set the contract states by name; every key is reported with zero; distinct attacker shapes get distinct reasons; a list the contract enumerates is held to its table by a test"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8774d8d571be9b7c
---

## A drop or refusal counter's reason labels are a closed set the contract states by name; every key is reported with zero; distinct attacker shapes get distinct reasons; a list the contract enumerates is held to its table by a test

Learned on InterWeave's `status.dropped_cards` (#356) and META_KEYS (#370), with
architect-cto ruling each time:
- An operator reads the reason names, so they are contract text (CHANNEL-EVENT.md states
  all twelve), not code's to choose. A new fault class the parser grows (key, signature,
  unreadable: three times in two days) is a change to that sentence. Ask for it; never map
  it silently onto an existing reason.
- A parenthetical list of examples in a contract is not the set. When code needs a closed
  set, ask whether the list is closed. Here it was examples, and the set was then written
  out.
- Every reason is present in status with its count, zero included: a missing key means a
  build that does not know the reason.
- Split reasons where the attacker shapes differ. A duplicated key (well-formed, two
  meanings) is not unreadable JSON (no meaning). Merge only true variants of one fault
  (all envelope-wide faults are one reason).
- Count by a fixed map from the parser's fault; the log line carries the fixed label, never
  the parser's Display, which may hold peer text.
- When code carries a list the contract tabulates (meta keys), add a test that reads the
  contract's table and requires the list to match it in order. A stale list then fails CI
  instead of rejecting a valid event at runtime.

*Anchors: `interweave:architecture/contracts/CHANNEL-EVENT.md::dropped_cards`, `interweave:crates/claude/channel-core/src/card.rs::CardDrop`, `interweave:tests/desktop-e2e/tests/claude_channel.rs::the_key_list_is_the_contracts_table`*

*Observed 2026-10-22 (rust-services-dev)*

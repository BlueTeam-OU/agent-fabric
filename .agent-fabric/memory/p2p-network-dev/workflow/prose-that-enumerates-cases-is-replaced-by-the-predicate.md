---
role: "p2p-network-dev"
class: workflow
topic: "prose-that-enumerates-cases-is-replaced-by-the-predicate"
description: A comment or contract sentence that lists cases (error codes per class, the states in which a reply answers X) draws a new finding every review round; state the predicate or class the code decides on, cite the test that is its oracle, and…
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 34902ed3e53f5374
---

## A comment or contract sentence that lists cases (error codes per class, the states in which a reply answers X) draws a new finding every review round; state the predicate or class the code decides on, cite the test that is its oracle, and restate no members

The same failure has happened in two shapes, and each took three or more
review rounds:

- **A code comment listing a contract's error codes by class** (InterWeave
  #322, 2026-10-20, `close_exchange` in tests/android-e2e-cases). It
  overclaimed, then put an example in the wrong class, then missed codes in
  "complete" lists. It was ended by naming only TRANSPORT.md's three class
  headings (bae27538).
- **A contract sentence listing the states in which a disconnected reply
  answers ChannelNotJoined** (CHANNEL-EVENT.md §Delivery, #221 then #222,
  2026-10-07). Four rewrites ("never held", "re-join pending", "holds"…)
  each missed a reachable state: a held channel the host left, then a
  cancelled join, then the session's end. It was ended by keying the
  sentence on the predicate the code actually tests, the bridge's current
  membership (`reply_route`'s `is_joined`): held → BackendUnavailable, not
  held for any reason → ChannelNotJoined. A four-state test,
  `a_disconnected_reply_with_a_join_pending_answers_by_membership`, was
  named in the text as its oracle (architect-cto, 93ddb4d9).

**Why:** a list is a second copy of a decision the code makes from one
predicate or one normative table. Every rewrite is checked against the
code, and every list misses a case.

**How to apply:** when prose must say how the code decides, state the
predicate or cite the contract section and its class names. Never list
members, even "e.g.". Point at the test that drives the cases. On the
SECOND finding about the same sentence, stop patching and rewrite it this
way, or send the owner the predicate if the text is another lane's.
Related: [[workflow-to-role-finding-goes-to-the-holder-in-the-crate]].

*References: workflow-to-role-finding-goes-to-the-holder-in-the-crate*

*Anchors: `interweave:apps/claude-channel/tests/fake.rs::a_disconnected_reply_with_a_join_pending_answers_by_membership`, `interweave:tests/android-e2e-cases/src/lib.rs::close_exchange`*

*Observed 2026-10-25 (p2p-network-dev)*

---
role: "rust-services-dev"
class: domain
topic: "adapter-composed-text-indistinguishable"
description: An adapter feeding an LLM host never composes its own text into the content body; facts it derives go in structured metadata, because unescaped content is indistinguishable from peer text
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 83a02608a2aa1026
---

## An adapter feeding an LLM host never composes its own text into the content body; facts it derives go in structured metadata, because unescaped content is indistinguishable from peer text

If the host renders a channel event's content body unescaped (InterWeave CHANNEL-EVENT.md
§Sanitization), anything the adapter writes there can be forged by a peer sending the same
words as a plain text payload. Say the adapter summarises: "contact card from <peer>: name
X, a photo of N bytes, not shown". Any peer can send that sentence verbatim, and the model
cannot tell them apart.

What was decided instead (architect-cto DECISION 01a15d3c): content is "" and the derived
facts go in keys only the adapter can set (`app_kind`, `card_*`). Each value is checked
against the contract's bounds before it enters meta (a closed key set, no control
characters, a value-length bound that a legal value provably fits, asserted at compile
time).

**How to apply:** when asked to "present X to the model as …", put every adapter-derived
fact in metadata and leave the body to peer bytes. Then add a test that a peer text payload
spelling the metadata (or a forged tag) arrives as content with no such keys. A request
worded as prose rendering is a contract change: raise it with the contract's owner before
writing code (here it needed a CHANNEL-EVENT §Content exception).

*Observed 2026-10-22 (rust-services-dev)*

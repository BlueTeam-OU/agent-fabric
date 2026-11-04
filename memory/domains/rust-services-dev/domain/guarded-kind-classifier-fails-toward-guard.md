---
role: "rust-services-dev"
class: domain
topic: "guarded-kind-classifier-fails-toward-guard"
description: "When a classifier decides whether a payload takes a protective path, a malformed or unreadable instance of the guarded kind must classify as that kind (three-way answer), never fall through to the forward-raw path"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 873eb47094eff1e4
---

## When a classifier decides whether a payload takes a protective path, a malformed or unreadable instance of the guarded kind must classify as that kind (three-way answer), never fall through to the forward-raw path

An adapter that treats one payload kind specially (InterWeave's Claude bridge: a
contact_card goes to the model as meta only, with the 32 KB photo never shown) still
forwards every other payload raw. So "is it that kind?" is a security decision, not a
detail. If the classifier answers only kind-or-not, a damaged instance of the kind reads
as "not", and goes out raw with the bytes the special path exists to keep back.

Seen twice:
- A duplicate member, or a duplicate `kind` with one copy `contact_card`, failed as a
  malformed envelope with no kind. The bridge would have forwarded it raw.
- In #351, a well-formed card beside JSON serde_json cannot hold (1e400, a lone surrogate,
  nesting 200 deep) classified NotCard. Fixed as `CardFault::Unreadable`.

**How to apply:**
- Ask the one owning parser (never a second one in the adapter) for a three-way answer:
  NotKind / Kind(value) / MalformedKind(reason). Anything carrying any marker of the kind
  is Kind or MalformedKind, whatever else is wrong with it. Decide this by the grammar
  (here, JSON's), not by what the deserializer can represent.
- MalformedKind is dropped and counted by a fixed reason, never forwarded.
- Put it in the parser's acceptance before the consumer builds on it.
- Test it with hostile siblings (duplicates, unrepresentable numbers or strings, depth),
  not only with bad fields inside the kind.

*Observed 2026-10-22 (rust-services-dev)*

---
role: "p2p-network-dev"
class: domain
topic: "json-schema-maxlength-counts-characters"
description: "JSON Schema maxLength counts characters (code points), not UTF-8 bytes — 2048 characters can be 8 KiB; when prose says bytes and the schema says maxLength, raise the conflict, and test the bound with multi-byte text so a `len()` check fails"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dcecfd2a102750e0
---

## JSON Schema maxLength counts characters (code points), not UTF-8 bytes — 2048 characters can be 8 KiB; when prose says bytes and the schema says maxLength, raise the conflict, and test the bound with multi-byte text so a `len()` check fails

InterWeave #147 (2026-09-29): LOCAL-IPC.md gave a diagnostic message limit as
"2,048 UTF-8 bytes" and the schemas said `maxLength 2048`. Rust `str::len()`
is bytes; JSON Schema counts characters, so the two differ for any non-ASCII
text. The contract owner ruled characters; constants went `*_BYTES` →
`*_CHARS`, checks use `chars().count()`, and the test sits at the bound with
"é" (2 bytes each): 64 accepted, 65 refused, and reverting to `len()` fails
it. Until a ruling: send within the stricter unit, read by the looser one,
and name the conflict in the code.

**How to apply:** any wire string bound — check which unit each document
uses before coding it, and never test a character bound with ASCII only.
Related: [[peer-defeatable-bound-is-the-contracts]].

*References: peer-defeatable-bound-is-the-contracts*

*Observed 2026-10-18 (p2p-network-dev)*

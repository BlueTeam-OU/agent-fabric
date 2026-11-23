---
role: "rust-services-dev"
class: domain
topic: "json-line-bound-encoded-size"
description: "A byte bound on a JSON line must measure the encoded form: control chars cost 6 bytes escaped, 7 when re-embedded in a JSON string"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f9210384ffbd43b6
---

## A byte bound on a JSON line must measure the encoded form: control chars cost 6 bytes escaped, 7 when re-embedded in a JSON string

A size bound stated on a payload does not bound the line that carries it. JSON escapes a control
character as `\u00XX`, which is 6 bytes. When that JSON is embedded again as a string, as an MCP
tool result's text is, the same character costs 7 bytes. In InterWeave, a 196,608-byte payload
became a 1,180,109-byte host line (measured in j60). Its base64url form is 262,144 bytes.

**How to apply:** compute the encoded size before writing. Measure every form the same event
takes, and bound the largest (InterWeave measures both the push line and the pulled form). When
the bound would be passed, choose the representation by size, falling back to base64url, rather
than truncating. Test with a worst-case escape payload and a plain one that must keep its normal
encoding, and assert that the measure equals the length actually written. In InterWeave this is
channel-core's MAX_HOST_EVENT_BYTES and host_event_bytes (#376), and the contract is
CHANNEL-EVENT.md §Content.

*Observed 2026-10-22 (rust-services-dev)*

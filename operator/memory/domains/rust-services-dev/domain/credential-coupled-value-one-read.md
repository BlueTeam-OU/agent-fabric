---
role: "rust-services-dev"
class: domain
topic: "credential-coupled-value-one-read"
description: "A value that must stay consistent with a rotating credential (a per-account pseudonym key) is read in the same atomic read as the credential, never from a second source"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 467126cc42822946
---

## A value that must stay consistent with a rotating credential (a per-account pseudonym key) is read in the same atomic read as the credential, never from a second source

When a secret's meaning depends on which credential it goes out with (agent-fabric-gateway
ADR-003 rule 17: an HMAC key per login and per subscription account, so one login's traffic
is not linkable across accounts), both values come from one atomic read. Two sources (a key
file or variable beside the token file) are read one after the other. An attempt that falls
between the controller's two writes sends the new account's pseudonym under the old
account's token. That one request links the two pseudonyms, the exact property the scope
exists for. No order of writes or reads closes that gap.

The decided shape (fabric-coordinator, REPLY 01a155e5): the key is line 2 of the token
file, written by the same atomic replace as the token. A malformed line 2 or a third line
refuses the whole file. A hash route with no key line refuses the attempt (503, nothing
sent), never sends the raw id. Env profiles, which never switch, use a second variable.

**How to apply:** for any value bound to a credential's identity (pseudonym key, account
id, a per-account rate figure), ask "can a reader see one without the other from the same
write?". If yes, co-locate them in the credential's own atomic write, or state the race as
a known limit and send it to the contract's owner.

*Observed 2026-10-22 (rust-services-dev)*

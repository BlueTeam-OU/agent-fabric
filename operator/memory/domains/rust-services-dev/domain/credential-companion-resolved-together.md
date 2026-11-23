---
role: "rust-services-dev"
class: domain
topic: "credential-companion-resolved-together"
description: A value that must match the backend credential (account id, org id) has to be resolved with the credential, per attempt; a static header diverges on an account switch
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - b9e7a15ef551ee98
---

## A value that must match the backend credential (account id, org id) has to be resolved with the credential, per attempt; a static header diverges on an account switch

Some backends take a companion value beside the credential, such as an
account or organisation id, and it must name the same account as the
token. If the proxy reads the credential on every attempt, the
companion value must be resolved on every attempt from the same source.
A value fixed for the session, such as a static header the client is
configured to send, pairs the new token with the old id as soon as the
account switches under a running session.

Check this whenever a backend credential has a companion value. Is the
credential source re-read per attempt? Can the account switch while the
process runs? If both are true, the companion value is per-attempt.
Otherwise, record why a static value is safe, so the case that makes it
unsafe can be recognised later.

The case that taught it is the gateway's ChatGPT backend with
`ChatGPT-Account-ID`, 2026-10-12. fabric-coordinator decided that a
static header is safe while the review engine runs one review per
gateway process, and that the per-attempt value (Stage 6 step 8) is
built when the engine becomes a resident session. The release notes
(agent-fabric-gateway packaging/release-notes/v0.3.0.md) record the
limit. They do not record that trigger.

*Observed 2026-10-18 (rust-services-dev)*

---
role: "edge-hosting"
class: workflow
topic: "credential-scope-covers-the-way-back"
description: "Asking for a provider token: scope it to the change's API calls AND its way back's, not to the README's deploy rights; a token that can't undo the change makes it irreversible for the token's life"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d63cd5faac54e858
---

## Asking for a provider token: scope it to the change's API calls AND its way back's, not to the README's deploy rights; a token that can't undo the change makes it irreversible for the token's life

Before asking anyone to mint a provider token (Cloudflare or any other), write out the change record's API calls: the change itself, its read-back verification, and every call of its way back. Then derive the scope from that list, per zone or resource. Don't start from the project README's deploy rights, which describe a different operation.

- **Way back.** The write rights the way back needs are part of the ask. Reverting a detach re-attaches a domain, which writes a DNS record. Without DNS Write there, the change can't be undone until a new token arrives.
- **Unused rights.** Rights the change doesn't use are left out, even when the README lists them. A plain deploy's D1, Pages or Routes rights don't belong on a token for a pause through the API.
- **Out-of-scope requests.** The scope also limits what a later request can get done. A new ask on a resource where the token holds only Read is a new token and a new owner decision. Say so, and don't work around it with a redeploy.

**Why:** in October 2026, my first token request for a Worker pause was built from the README. It left out DNS Write on the zone whose re-attach was the way back. The minter (architect-cto) compared the request with the tree and found the gap, and I corrected the ask before the mint. A later request to attach a hostname in the other zone then hit the Read-only scope there.

**How to apply:** in the REQUEST, list each right next to the call that needs it ("DNS Write on <zone>: the way back re-attaches <host>"). Ask for the expiry to cover the time the way back must stay possible. Record the expiry in the change's thread memory. Related: [[cloudflare-worker-has-no-pause]], [[agent-store-tool-only]], [[publish-needs-owner-word-in-session]].

*References: agent-store-tool-only, cloudflare-worker-has-no-pause, publish-needs-owner-word-in-session*

*Anchors: `gzapp:apps/status_web/README.md::Requires Cloudflare API access`*

*Observed 2026-10-30 (edge-hosting)*

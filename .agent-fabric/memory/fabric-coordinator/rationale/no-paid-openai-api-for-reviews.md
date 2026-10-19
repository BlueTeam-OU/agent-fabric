---
role: "fabric-coordinator"
class: rationale
topic: "no-paid-openai-api-for-reviews"
description: "Owner 2026-10-13: Codex reviews use the ChatGPT subscription only — never the pay-per-use OpenAI API, even when the subscription's Codex allowance is spent"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b10b330784d76517
---

## Owner 2026-10-13: Codex reviews use the ChatGPT subscription only — never the pay-per-use OpenAI API, even when the subscription's Codex allowance is spent

2026-10-13 evening the ChatGPT team workspace's Codex allowance ran out ("Your workspace is out of
credits"), blocking every arm (policies/arming.json requires claude + codex). The chat in the web
app still worked. I proposed a gateway fallback to the fleet's OpenAI API key with a daily cap. The
owner: "no. I pay for a subscription to use it and i will not pay more to do something that from the
web interface i'm able to use. so if there is an endpoint where the chatgpt web use good else bad we
don't use it".

**Why:** the subscription is already paid; per-token API spend for the same model is refused.
**How to apply:** never route the codex engine to OPENAI_API_KEY. The subscription's programmatic
path is Codex through the gateway (ChatGPT sign-in, [[codex-chatgpt-signin-2026-10-12]]); the web
chat's private endpoint is not a supported API for subscription use (automating it risks the
account), so it is not used either. When the Codex allowance is spent: wait for its window, or the
owner decides the arming policy; cap how often the fleet runs Codex so it is not spent again.

*References: codex-chatgpt-signin-2026-10-12*

*Observed 2026-10-13 (fabric-coordinator)*

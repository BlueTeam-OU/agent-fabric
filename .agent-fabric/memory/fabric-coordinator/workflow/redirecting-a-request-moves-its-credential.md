---
role: "fabric-coordinator"
class: workflow
topic: "redirecting-a-request-moves-its-credential"
description: When a fix changes WHERE a request goes, list every credential that travels with it first — clearing the destination alone can send a secret to a third party
tier: 1
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 0b17494c95e6e567
---

## When a fix changes WHERE a request goes, list every credential that travels with it first — clearing the destination alone can send a secret to a third party

On 2026-09-23 (PR #31) a nested `launch --provider anthropic` from a
broker session inherited OpenRouter's `ANTHROPIC_BASE_URL`, so it ran on
the broker while stamped "anthropic" — a P1. I fixed it by clearing the
base URL and `ANTHROPIC_AUTH_TOKEN`. The re-review found that `ori claude`
puts the account's **OpenRouter key in `ANTHROPIC_API_KEY`** (and sets
`ANTHROPIC_AUTH_TOKEN` to an empty string). My fix kept the key and
removed the URL, so the child would have sent the OpenRouter secret to
`api.anthropic.com`. Before the fix it went to the host it belonged to.
The fix made a worse P1 than the one it closed. My comment beside it
claimed "whatever credential rides with it for that host" was cleared —
an unverified safety claim, the same failure as
[[a-wrong-why-outlives-the-code]], with a secret at stake.

**Why:** a destination and its credential are one unit. Changing only the
destination doesn't make the request safe; it re-addresses the secret.
The variable that *looks* like the credential (`AUTH_TOKEN`) was empty;
the one that held it had a different name. Nothing ran it only because the
PR was not yet armed.

**How to apply:** before clearing or changing a base URL, endpoint or
proxy, read what the *setter* actually puts in the environment (the
binary or source, not the variable names you expect), list every
credential and header bound to that destination, and move them together.
Add a second, destination-independent check on the secret itself
(`equals the other provider's key`, or its prefix) so one missed variable
cannot leak it. Test credentials by SHAPE (`unset/empty/sk-or/sk-ant`),
never by value, and grep the suite log afterwards for the real key. A
security fix is re-reviewed on its own range before anything is armed.

*References: a-wrong-why-outlives-the-code*

*Observed 2026-09-23 (fabric-coordinator)*

---
role: "rust-ui-dev"
class: domain
topic: "effective-state-from-the-operation"
description: "A client choosing among server-side resources (which endpoint to claim, which ssh-agent holds a key) -- use the operation's own answer as the effective state, not a separate list read"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0103ab20a786729c
  - 8261f3b29defcf96
  - eebccf822929019e
---

## A client choosing among server-side resources (which endpoint to claim, which ssh-agent holds a key) -- use the operation's own answer as the effective state, not a separate list read

Once a server persists admin changes (an endpoint disabled survives its restart), a client
that picks its resource from the authored config file picks a disabled one forever. My
first plan was to read the server's effective list; that needed an admin authority (which
can also disable and revoke) the chat client has no use for, and a list read races the
claim. What shipped: try the configured candidates in order and move on only on the
specific "disabled" refusal; any other refusal stops. The claim's answer IS the effective
state, so nothing races and no extra authority is held. Prove it end to end (disable,
restart the service, the shipped binary takes the next candidate; fails with one candidate).

Seen again (2026-10-23): a client learnt "the list is switched off by the operator" only
from a row flag or an add's refusal, and lost it when the list became empty. Remembering the
"off" across reads was rejected: nothing can correct it if the operator turns the list back on,
so a button would refuse falsely. The action opens, and its own refusal says why -- always true,
at the cost of one tap. Do not cache a negative fact the client cannot re-observe.

Seen again (2026-10-30, ssh-agent choice): a desktop keyring proxy socket lists every public
key in ~/.ssh whether or not anything holds it, so "ssh-add -l lists the fingerprint" picked
it, and 25 panes then asked for the passphrase. Holding is proven by the operation: a
signature the agent makes without prompting (`ssh-add -T` with the public half). A sign
request to such a proxy can open a desktop unlock dialog instead of failing, so the probe
runs with stdin closed and a timeout, a dialog counts as not holding, and a socket known to
be a listing proxy is never asked at all.

*Observed 2026-10-31 (rust-ui-dev)*

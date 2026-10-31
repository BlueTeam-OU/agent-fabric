---
role: "rust-ui-dev"
class: domain
topic: "network-denied-posture"
description: "Designing a client's state when the platform refuses it network access (Android 17 runtime INTERNET) -- local data stays usable, no false promise, one action"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1ecf789045a39493
---

## Designing a client's state when the platform refuses it network access (Android 17 runtime INTERNET) -- local data stays usable, no false promise, one action

On Android 17 (API 37) INTERNET is a runtime ("dangerous") permission: a fresh install does
not hold it and the first socket fails EPERM. The client journey that was ruled:
- ask for network before binding the service; notifications only after (network is
  essential, notifications optional);
- denied: a distinct state with one primary action (the platform prompt, or the app's
  settings once the platform stops offering it). Never the generic "will connect when the
  service starts" text: with the permission refused it never will;
- the person's data stays usable without a network. "Read-only" was the first ruling and
  was wrong: where reading is itself a local write (a read deletes an unkept message, Keep
  writes), the store must open normally, with no runtime, no lease, no sending;
- a background "stay reachable" service restarted without the permission posts one
  notification and ends -- never a silent stop, never a retry loop.
- A typed refusal for "the platform refused a socket" also fires for bind() below port 1024
  (EACCES): before showing the permission state, check the permission itself.

*Observed 2026-10-15 (rust-ui-dev)*

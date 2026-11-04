---
role: "rust-ui-dev"
class: domain
topic: "network-denied-posture"
description: "Designing a client's state when a start is refused for something the person must act on (Android runtime INTERNET denied, a user-presence key locked) -- offline with its cause, no false promise, one action, a declined prompt never…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1ecf789045a39493
  - 29318477ad1c9938
---

## Designing a client's state when a start is refused for something the person must act on (Android runtime INTERNET denied, a user-presence key locked) -- offline with its cause, no false promise, one action, a declined prompt never re-raised by itself

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

Seen again, 2026-10-19/20, with a key that needs the person's authentication (Android
user-presence policy): a cancelled system prompt left the client reading "Status not known"
plus "will connect when the service starts" -- the generic no-service state. The same rules
held, so they belong to the class "start refused for a person-actionable reason", not to the
permission:
- the line reads offline, never unknown, and the notice names the cause and its one action
  (Unlock); nothing beyond that on a cancel -- no error snackbar for the refused start;
- a declined prompt is never raised again by the app itself. A return from Home or Recents to
  the same Activity shows the notice and waits for the action; only a cold launch (a new
  Activity) prompts before binding. That a launch "counts as presence" decides whether a
  prompt is allowed, not whether to raise one unasked: re-prompting at each app switch
  punishes switching and overrides the person's no;
- check what the state really offers before briefing its words: here the store opened only
  with the service, so nothing was readable or sendable -- the brief had claimed both
  ([[brief-facts-checked-first]] in the project memory).

*References: brief-facts-checked-first*

*Observed 2026-10-24 (rust-ui-dev)*

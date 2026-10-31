---
role: "rust-ui-dev"
class: domain
topic: "uncertain-outcome-state-and-copy"
description: "How a client shows an operation whose outcome is unknown -- classify by dispatch state, monotone may-have-reached, copy that never claims nothing changed"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c986b8466a8799f7
---

## How a client shows an operation whose outcome is unknown -- classify by dispatch state, monotone may-have-reached, copy that never claims nothing changed

Classify every failure of a remote operation by dispatch state, then derive both the model
state and the copy from that class:
- Failed before dispatch: "nothing was changed" is true and may be said.
- Failed after the request may have been written (timeout, cancel race, connection or service
  ended, internal error): the outcome is unknown. Show "not confirmed / may have been made",
  never "failed" or "nothing was changed", and say what the client does next (retries, reads again).
- "May have reached" is monotone: once true it stays true until terminal, a later
  transient error does not reset it, and it survives a restart (persist it, or derive it
  conservatively, e.g. attempts > 0 when the attempt is recorded before the transport call --
  over-stating "may" is the safe direction). Cancel carries it too (Cancelled { may_have_reached }).
- A follow-up read that itself fails must not fall back to the generic "nothing was changed"
  text; say the shown list may be stale and how to re-read.
- Copy must not point to diagnostics nobody keeps.
- A version-skew refusal (older service) is its own problem with its own text, never folded
  into a generic failure: the person can act on it.

Seen twice: the send-status contract of a messaging client, and its trust-settings page,
where a blind review found "Nothing was changed" shown for outcome-unknown failures three times.

*Observed 2026-10-15 (rust-ui-dev)*

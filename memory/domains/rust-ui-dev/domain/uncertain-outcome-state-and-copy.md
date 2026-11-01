---
role: "rust-ui-dev"
class: domain
topic: "uncertain-outcome-state-and-copy"
description: "How a client shows an operation whose outcome is unknown -- classify by dispatch state, monotone may-have-reached, copy that never claims nothing changed"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0248b68a115b2930
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

Local writes too (2026-10-19, an identity seal and restore, three review rounds): a write
that can refuse after it published (the directory fsync after a rename; a failed retire of the
old key) leaves its outcome unknown, so "nothing changed" is false there. Read back to decide --
but only for the refusals that can come after the publish (here Storage(Unsynced) and
OldKeyRemains), and only with a check the old state cannot already pass: reading back a field
the old record shares reported a restore as done when nothing was written; opening the record
with the new key does not. A refusal before the publish is reported as itself.

Admin writes on a list screen (2026-10-22/23, many review rounds) added the rules for what
comes after an unknown outcome:
- Map every failure to one of four outcomes: not written (never left) / unknown (left, no
  answer) / not permitted / incompatible -- the last two with no Try again.
- **An unknown change stays unknown until a read shows it.** A retry of it that fails before
  writing keeps the unknown line; it never shows the not-written text, which is false for the
  first attempt. Track it per item (per line, per PeerId), every unknown one, not only the
  latest; a refusal settles nothing; only an answer that states the item's presence, or a
  successful read that STARTED after the write was sent, decides it.
- Even that read is best effort when the server orders requests by queue entry and not by
  connection: a lost write can land after a later read on another connection (a lost allow,
  a revoke answered ok, then the late allow). Ask the server owner for its ordering, state the
  limit in the PR, and take a contract (request token, drained connection) when one is ruled.
- All-or-none over N items cannot be built from N single writes (a refusal or kill midway
  leaves a partial write); ask for a batch method that checks the whole list first.
- Back or Escape while a write is in flight closes the page (a Back that does nothing breaks
  the platform); the write goes on and counts as a lost answer. Hold the field read-only and
  show a waiting label that claims no outcome, its progress mark kept under reduced motion.

*Observed 2026-10-24 (rust-ui-dev)*

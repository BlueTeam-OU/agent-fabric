---
role: "language-culture"
class: domain
topic: "slot-decides-value-sentence-shape"
description: before a value becomes a sentence, two sentences or a fragment, read the template or code that joins it; the slot it fills decides its shape and its end punctuation
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7100e64803692cb3
---

## before a value becomes a sentence, two sentences or a fragment, read the template or code that joins it; the slot it fills decides its shape and its end punctuation

A value is often not shown alone. A template or the code puts it into
a longer text, and that container decides the value's shape: a whole
sentence, one sentence only, or a fragment, and whether the value ends
in a full stop. Two cases in InterWeave, W44:
- CardSentPhoto changed from a fragment to a whole sentence ("The card
  includes your photo."). The code joined it to the name with ", ", and
  the label template added ". " after the body. The spoken label would
  have been "Ada Lovelace, The card includes your photo.. Sent". I told
  rust-ui-dev-02 that the join was theirs to change. On origin/main
  (817ac44b0) `lib.rs` now puts the photo sentence after its own full
  stop and removes the template's second one.
- Every ErrorClass reason fills `NotSent => "Not sent: {reason}"`, and
  every reason there is one sentence. A two-sentence draft for
  NotSentEndpointLimit was joined with "so", and its reworded version
  with a semicolon, to stay one sentence after "Not sent:".

**Why:** a value is reviewed as a string alone, and a string alone looks
right in either shape. The fault shows only in the assembled text, which
is spoken by a screen reader or shown by code that I do not own.

**How to apply:** when a change adds or removes a sentence, or adds or
drops the final punctuation, find every place where the key is used
(`git grep` the key name, then the template that holds its
placeholder). Read the assembled result with a real value. Keep the
shape that the slot's other values have. If the code's join must
change, say so to the code's owner in the REPLY with the assembled
text as it would read. Do not choose a worse shape for the value to
avoid that change.

Related: [[uncontrolled-value-away-from-punctuation]], [[announced-text-is-heard-not-seen]], [[key-value-true-in-every-state]]

*References: announced-text-is-heard-not-seen, key-value-true-in-every-state, uncontrolled-value-away-from-punctuation*

*Observed 2026-10-31 (language-culture)*

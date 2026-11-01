---
role: "ux-designer"
class: domain
topic: "strings-claim-only-what-is-true"
description: "When specifying what a string must communicate, also write what it must not claim: no step the platform lacks, no scope wider than the action, no promise that will not come by itself"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5d1f544c60a75e2b
---

## When specifying what a string must communicate, also write what it must not claim: no step the platform lacks, no scope wider than the action, no promise that will not come by itself

The words are language-culture's, but what a string may claim is
behaviour, and it fails in three recurring ways:
- it advises a step this platform cannot do ("contacts and settings are
  restored separately" on an Android with no export);
- it names more than the action affects ("Move this PeerId" when Move
  took one conversation; "the only route" when a second existed);
- it promises what will not happen unaided ("the app will connect when
  the service starts" when only the person's unlock could start it;
  "no setting limits this yet" for a setting no record plans; "might
  find their address by itself" where discovery is not on; "connects
  to" where the device only tries);
- it is true in one case it covers and false in another: "This device
  already holds {max}" became false once a several-line add could pass
  the bound from below; "the address you acted on" was false when focus
  only sat on the row; a line that leaned on a neighbour (IdR1Settings)
  stood alone on another screen (K1) and lost its half; "No code was
  found in this image" with no image on the clipboard; "Folder:" for a
  plain file; "cancels it" for a card the transport already took.
**Why:** InterWeave identity note (#303, 2026-10-19), Android review
(#309, 2026-10-19) and contact-card spec (#334, 2026-10-21), add-a-peer and android-identity (#365, #396, 2026-10-22/23): each was
caught by language-culture-en, a developer or a review, not by the spec.
**How to apply:** in each strings-table row, besides what the text must
say, write what it must not claim (platform steps, scope, future). Check
an advised step exists on each platform before the row is written; when
the scope rule of an action changes, re-check every string of that
action. When a rule widens the cases a row covers, or a string shows in
another place, re-read it in each case and each place, without the
neighbours that are absent there.
Related: [[labels-as-whole-templates]], [[declined-prompt-stays-declined]]

*References: declined-prompt-stays-declined, labels-as-whole-templates*

*Observed 2026-10-25 (ux-designer)*

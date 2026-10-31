---
role: "language-culture"
class: workflow
topic: "key-value-true-in-every-state"
description: "before writing a key's value, read the code path that shows it — the value must be true in every state, platform and reader that path reaches"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 23466a2cb22d8cf9
  - 96a653a88e58b623
---

## before writing a key's value, read the code path that shows it — the value must be true in every state, platform and reader that path reaches

A key's name and its draft say what the caller thinks the key means. The code that selects the key says when it is really shown. Four cases this week where the two differed:
- gzapp `common.health.summary-not-configured` is shown when **any** check is unconfigured (summariseHealth.ts). "No checks configured" (all) was false in the mixed state. The blind review of gzapp#1079 found this in my own value, and the ka-GE and ru-RU values had the same sense.
- An on-request hint said "here", but in the not-yet-boarded state the line above it names the rider's destination. A cold reader took "here" to mean the destination (gzapp#1119).
- `error.admin.stop-restriction.state-invalid` fires only on a bad query parameter that the screen never sends. Its reader is a developer, so it keeps the API's values (draft, active, retired), not the screen's words.
- Shared InterWeave `labels.rs` values named "the transport daemon" and "the window". These are false on Android, which has no daemon. The decision was a platform value per key.

**Why:** a value that reads well in the state the writer imagined can still be false in another state. Neither the validator nor a cold read of the text alone sees it.

**How to apply:** for each key, find where the code selects it and list the states, platforms and readers that reach it. Write the value so it is true in all of them. When no single text can be true in all of them, say so to the caller as a key change (a second key, a count, a platform value). Do not soften the words.

Related: [[dictionary-value-has-readers-outside-the-dictionary]]

Instance (2026-10-15, gzapp#1119, commit 01ec57223): a ruling worded once for two states ("look for the rider", pickup and dropoff) does not read the same in both. At the dropoff the passenger is aboard, and a cold read of a bare "Look for them" did not know what to do. The words of a ruling are its meaning, not its copy: say where, per state ("on the bus").
Second instance, same day (commit da431e919): one key that serves several roles (the driver heads-up body, for pickup and dropoff) must be true for all of them; I gave it "look for them", true only at pickup. And "say the stop's name" is false where a stop has no name, which the driver app says is common: read the code for every value a referenced thing can take (named / unnamed), not only the role.
Third instance (2026-10-16, InterWeave#289, UiText::Restored): the snackbar after every Undo read "Restored", but the Undo of Keep leaves the message not kept, so nothing is restored. "Action undone" is true after every action that reaches the key (01a144ec-6faa).
Fourth instance (2026-10-19, InterWeave android-identity note, b85d0bae): one PeerId label was asked for on C2, S2, C4 and R4, but "write it down" is false on C4 and R4, where the person has already written it. The cold read found it, and the label became two keys.
Fifth instance, same note (6dcb9d3e): a line asked to say "restored separately" would advise a step the platform may not offer. While that is unknown, state the fact only ("not part of them"), and say when the line gains the step.
Sixth instance (2026-10-19, #303 r1, 41ca6ef0): when behaviour adds a state (K1 with no readable PeerId, where the phrase cannot help), every existing text shown in that state must be read again. Three of them ("needs your recovery phrase", "Restore it with...", "If your words are lost") became false without being touched. And a requested "this phone" was false on a move to a new phone, so the text names the PeerId "that goes with them".
Seventh (#303, 3967fb10): my fact-only line, which a review had overruled toward "needs a separate backup", was reinstated once architect-cto confirmed that Android has no export. When a text would advise a step, ask whether the platform offers that step before you accept the advice.
Eighth (#303, cb479977): a state with no text at all is also a text decision. A silent transition after the person acted (a restore that read back another identity) can mislead as much as a false string, so ask whether it needs words.
Confirmed: ux-designer-01 added IdRestoreOther for that silent case (13f1e9c5), so the question was worth asking.

Instance 9 (2026-10-19, InterWeave F10, j81): a brief described the
problem classes in its own words, and one description was wrong
("not reachable on the route" was really the peer answering with
RemoteEndpointUnavailable). Read the code that classifies them
(transport-client problem.rs, classify_send) before writing a text
for a class, not after. The brief is a paraphrase.

Instance 10 (2026-10-19, InterWeave F11, j82): a dialog label "PeerId"
for Details. The key it replaces (ConversationId) says that Details
shows "a direct route's PeerId or a channel's id". Read the doc comment
of the key being replaced: it names every case the new text must hold
in. A cut line is a state too: at 200 %, two texts that share their
first 18 characters look the same.

Instances 11 and 12 (2026-10-19 and 2026-10-20, reflection W43): the
brief itself was wrong twice more, and each time its author corrected
it after I had started. The user-presence notice's brief said received
messages "stay readable" and what is written "is kept and sent"; both
were false, because the store opens only with the network service
(01a1550f-f5dc). The release page's brief said an older release "does
not start" after a newer one; that holds only when the newer one
changed a format (01a15825). With instance 9 that is three briefs in
two days. A sentence in a brief that the text will promise to the
person (kept, readable, refuses, nothing lost) is the one to check in
the code, or to ask about, before the text promises it.

Reflection 2026-W43 (second pass): the states to list include **the
screens where the key shows, each with its own neighbours**. I cut
IdR1NewKeys's positive half because IdR1Settings said it on R1. On K1
the line shows without IdR1Settings, so the review found it incomplete
(#396 F2, 01a1674a). In the same week, three texts were split into two
keys, or kept as one text only after I listed every case: PeerRowGone
(four focus cases, two keys, 01a1683e), CardUndoHint (a state with no
composer, 01a16e03), and KeyDirUnsafe (a link, a folder another account
owns, or a file). Ask the author for the case list. A Where cell that
names "two cases" has more than once had three or four.

*References: dictionary-value-has-readers-outside-the-dictionary*

*Observed 2026-10-25 (language-culture)*

---
role: "language-culture"
class: workflow
topic: "key-value-true-in-every-state"
description: "before writing a key's value, read the code path that shows it — the value must be true in every state, platform and reader that path reaches"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 23466a2cb22d8cf9
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

*References: dictionary-value-has-readers-outside-the-dictionary*

*Observed 2026-10-18 (language-culture)*

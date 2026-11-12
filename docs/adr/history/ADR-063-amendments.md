# ADR-063 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-11-12 — the assist key is the operator's configured key, and the title says so

What changed: the title, Scope, §2, the second alternative of §3 and rule 1
no longer name one account's API key. They say "the operator's configured
assist key", a `CLAUDE_APIKEY_*` entry in the host operator's store whose
name is configuration and a single constant in the assist module, not the
record's. The title reads "fabric-ctl assist: the owner's questions on the
operator's assist key". §1's account of the incident that prompted the
record is narrative and is reworded at publication.

Why: ADR-045 §5 rule 4. Rules 2-9 (the operator's terminal only, advice
never action, spend recorded) hold for any operator; which key is this
organisation's account. The record is Proposed, so the amendment retitles
it instead of replacing it with a new number
(docs/split/adr-classification.md, ADR-063 row and "Decided").

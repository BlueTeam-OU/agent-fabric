---
role: "architect-cto"
class: workflow
topic: "gzapp-journey-call-sign-decision-2026-10-15"
description: "The owner's three choices behind gzapp ADR-078 (journey call sign, driver sees it only when the phone is silent, silence anchored on the ADR-077 wake) and why each alternative lost"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6307187b7aae6104
---

## The owner's three choices behind gzapp ADR-078 (journey call sign, driver sees it only when the phone is silent, silence anchored on the ADR-077 wake) and why each alternative lost

On 2026-10-15 the owner decided that every activated gzapp journey carries
a four-character call sign (letters and digits mixed, no I, O, Q, 0, 1),
unique per city among unreleased journeys, shown in the passenger app for
the journey's life, so a driver can call out "this is <SIGN> stop" at the
pickup and at the alighting stop when the rider's phone is dead.

The three choices, with the alternative each rejected:

- **Shape: 4 mixed characters** over "4 letters + 1 digit" and "3 letters +
  1 digit". 31 symbols give ~923k signs per city; a composition rule buys
  nothing when the sign is spoken, so none is imposed (stated assumption).
- **Driver sees the sign only once the phone is silent** over "always with
  a silent flag". Ordinary pickups stay location-only, so the directive
  contract's "never a passenger identifier" reading is narrowed, not
  dropped.
- **Silence anchored on the ADR-077 wake** over a contact-gap rule. Android
  doze suspends the app's poll and iOS is foreground-only, so a healthy
  pocketed phone and a dead one look the same by gap alone; a wake that
  goes unanswered is the only proof the phone could not answer. iOS has no
  wake, so it is `not_evaluable` and never flagged (accepted limitation).
- **Both moments**: the owner added that the sign serves the aboard rider
  too (the driver must know to stop), so the alighting-approach wake is the
  second anchor and silence never blocks the dropoff directive, which rests
  on ADR-053's motion-inference boarding fallback.

**Why:** the record (ADR-078, branch
`develop-qzapp/architect-cto-01/adr-078-journey-call-sign`) carries the
decision; this note is the staging copy until it merges, then it is
promoted and should be deleted.

**How to apply:** cite ADR-078 for the sign and the reachability rule;
never let a lane reintroduce a gap-only "silent" rule or show the sign on a
reachable journey's directive. See [[review-economics-measured-2026-10-14]]
for the review flow the ADR PR goes through.

**State (2026-10-15 17:20Z):** gzapp #1120 open (3 work, 0 fix), blind
review dispatched on head ca352c6c; requests sent — db-admin
01a1408f-c99e-7afb-87b8-8982a35d6acc (migration), backend-dev-01
01a1408f-cecd-7ac6-af70-5e2436200cd3 (mint, evaluator, notice, the
snapshot 1.1.0 activation change), flutter-dev-01
01a1408f-d44d-7698-aa5b-90587c6d2c06 (rider sign, driver notice).
Owed to me: nothing from the lanes (db-admin undertook 01a14091-4f6f: branch develop-qzapp/db-admin/feat/journey-call-sign, migration 0014, PR after #1120 merges); backend-dev-01 undertook (j30, branch develop-qzapp/backend-dev-01/feat/adr-078-call-sign-reachability, cut after #1120 and the migration; outbox row carries no sign, reading (b) confirmed 2026-10-15); flutter-dev-01 acknowledged 01a14090-92cd as job j26 on #1119's branch (further commits after #1120 merges; fresh branch feat/journey-call-sign if #1119 merges first). Owed by me: the snapshot 1.1.0 contract
commit onto backend-dev's branch if they ask for it; arming of #1120 is
the owner's (under the ADR-019 minimum).

**Round 1 (2026-10-15 17:35Z):** blind review of ca352c6c: no P1, five
P2, two P3; F3–F5 adjudicated blind and upheld. Answers on head
f0690837 (#1120: 3 work, 2 fix): the sign is released by the row's
deletion at delete_after (no release column; unique index over every
row); silence anchors on journey_wake_sent, a wake without a sent
outcome is not_evaluable; last_contact_at is a wall-clock occurrence
stamp judged on one clock (ADR-017 r4, r19). Lanes told (INFO
01a1409f-9a58 db-admin, 01a1409f-a209 backend-dev-01). Delta re-review
dispatched on f0690837.

**Round 2 (2026-10-15 17:48Z):** re-review of f0690837 fixed F1, F2,
F4–F7; F3's answer failed on a fact: runtime_events are never deleted
(ADR-028 r10, trigger 0009), so the sign now lives in NO event
(journey_activated dropped it; a rebuilt row has no sign). Also the
reachable event's `since` is the evaluation's instant, stale wording
cleared, lower-case fixture added. Head d302fb2b (#1120: 3 work, 3 fix),
round 3 dispatched. Owner said "merge 1120" at ~17:40Z: arm once the
head's review posts clean. Lesson: before promising an age-out, check
ADR-028 rule 10 — the stream is permanent. flutter-dev ruling sent
(01a140a8-e363): sign stays on the lock screen.

**Armed (2026-10-15 17:58Z):** #1120 (3 work, 4 fix) armed on the owner's
word "merge 1120" after four blind rounds (head b55196b3 clean of
P1/P2). Open for a follow-up amendment (job added): round-4 P3 — a row
rebuilt mid-journey re-mints a sign the silent rider never saw; the
notice should omit a sign minted after the last contact. Owner ruling
still open: "sent" anchor (journey_wake_sent) versus "issued". Pre-
existing: every regime_4b kind says "aged out per the 4B row" while
ADR-028 r10 forbids deleting runtime_events. The arm tool wants the
literal phrase "owner's word" in --basis for an under-minimum PR.

**Merged (2026-10-15 ~18:40Z):** #1120 merged as 7bc99120d after five rounds; j131 delivered. The three choices are now ADR-078's record (promoted); this file stays for the follow-up state (j133) and the review lessons.

**Ruled 2026-10-15 18:51Z (for j133's amendment):** flutter-dev-01 asked
how a Latin sign is said aloud in ru/ka (QUESTION
01a140e4-a48f-7136-af08-b0a4d5f2b700). Reply 01a140e7-4bf1: the sign is
recognised, not transcribed; each speaker reads the glyphs in their own
locale; alphabet unchanged (a Latin/Cyrillic look-alike restriction would
collapse the space and does nothing for Georgian script); nothing on the
client. Owed in the j133 amendment: §6 accepted limitation made explicit
(driver and rider reading Latin letters in different locales), a §7 line
(a per-locale spelled-out reading beneath the sign, authored by
language-culture, if field evidence shows mis-recognition), history note
citing both message ids.

*References: review-economics-measured-2026-10-14*

*Observed 2026-10-15 (architect-cto)*

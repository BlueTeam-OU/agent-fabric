---
role: "flutter-dev"
class: domain
topic: "i18n-slot-holds-a-bare-value"
description: "A copy placeholder carries one bare value whose grammar the formatter fixes — a day or other qualifier gets its own key chosen by a local-date comparison, and the date skeleton is the locale holder's call because intl's forms carry case…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d2b3a02e44a5f54c
---

## A copy placeholder carries one bare value whose grammar the formatter fixes — a day or other qualifier gets its own key chosen by a local-date comparison, and the date skeleton is the locale holder's call because intl's forms carry case and abbreviations.

Four times the same shape: a client wanted to put more than a value
into a `{time}`/`{date}` slot, or chose the date format itself.

- **The qualifier breaks one language or another.** "tomorrow 05:30"
  inside `{time}` is harmless in Georgian (it inflects the END of the
  slot) and ungrammatical in Russian (a preposition governs it from the
  FRONT: «в завтра 05:30»). So "service resumes tomorrow" became its own
  key, chosen by comparing the instant's local date with today's.
- **"Since 23:40" read at 01:10 needs its day** — and a stuck shift can
  be days old (domain-transit: a shift is a driver's act, not a
  timetable row), so the qualifier could not be "yesterday" either: a
  separate `-dated` key with `{date}` and `{time}`.
- **The formatter's grammar is not neutral.** ru `MMMd` abbreviates
  only eight months (мар., июн. read as broken), so the ru holder asked
  for `MMMMd`. ka `MMMMd` renders the month in the nominative only, so
  the Georgian dated line could not keep its sibling's opening and took
  a colon frame instead.

**How to apply:** a slot gets `DateFormat.Hm()` or a single bare value
and nothing else. Anything that would modify it (a day, "since", a
relative word) is a separate key the client picks by a deterministic
comparison (local dates, presence of a field). Offer the locale holder
the skeleton options and let them pick per locale; do not choose
`MMMd`/`MMMMd` yourself. Ask what bound the data has (how old can it
be?) before settling on "today/tomorrow" keys. The closed thread that
first recorded the slot rule: [[walk-only-plan-says-why-owed]].

*References: walk-only-plan-says-why-owed*

*Observed 2026-10-18 (flutter-dev)*

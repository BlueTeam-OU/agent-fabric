---
role: "language-culture"
class: domain
description: The Georgian defect families that recur across every gzapi surface — check these first before reading a new text line by line
tier: 2
knowledge_scope: full
distilled_at: "2026-09-18"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
  - clone_id: "clone-8a543ee5423d427c"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 101990863729552d
  - 52e5c950265c929b
  - 6bb3f2aca9990daa
---

## Intl.RelativeTimeFormat can silently fall back to another locale instead of erroring

A browser's/runtime's ICU data does not necessarily cover every locale a product ships. When a locale is missing, `Intl.RelativeTimeFormat.supportedLocalesOf([locale])` correctly returns an empty array, but simply constructing `new Intl.RelativeTimeFormat(locale)` anyway does not throw: `resolvedOptions().locale` silently reports whichever fallback locale the runtime chose (commonly `en-US`), and every string that formatter produces renders in that fallback language with no error, warning, or signal reaching application code. This was confirmed for `ka-GE` (Georgian) specifically, while `ru-RU` and `en-US` both resolved correctly — so locale coverage in built-in Intl formatters cannot be assumed uniform across a product's locale set and must be spot-checked per formatter (RelativeTimeFormat, DateTimeFormat, NumberFormat, etc. can each have different coverage) rather than inferred from one working.

## The Georgian defect families that recur across every gzapi surface — check these first before reading a new text line by line

Found in the gzapp locale dictionaries, the gzapi.ge site copy and two
decks (2026-09-17), independently each time. A new Georgian text is
worth grepping for these before reading it through:

- **Register.** English imperatives carry no politeness marking, so a
  first-pass Georgian translation picks შენ by default. Business- and
  agency-facing copy takes თქვენ; a rider's own voice keeps შენ. This
  is now brand decision 0007 — see [[georgian-review-gate]].
- **`-სა` before `და`.** Two genitives joined by `და` need `-სა` on the
  first (`ინოვაციებისა და ტექნოლოგიების`). A text usually gets this
  right in most places and wrong in one, so it reads as a typo rather
  than ignorance — and the one is often a proper name.
- **Animacy.** `გვყავს`/`ჰყავს` is for people and animals, `გვაქვს`/
  `აქვს` for things; an inanimate plural subject takes a **singular**
  verb (`მარშრუტკები ... არის`). Both slip when the noun is a vehicle.
- **`აშენება` for abstractions.** Products, platforms and companies
  are `შექმნილი`, not `აშენებული`; `მშენებლობა` is building
  construction.
- **False friends.** `სამუშაო პროტოტიპი` means "prototype to be worked
  on" (want `მოქმედი`); `გადასახადი` is a *tax*, not a fee (want
  `საფასური`); `გზამკვლევი` is a guidebook, not a roadmap; `მასშტაბი`
  is scale, not scope (want `არეალი`); `კადრები` is Soviet-era register.
- **Calques that parse but are not Georgian.** `ცოცხალი მდებარეობა`
  for "live" (want `რეალურ დროში`), `შემოსავლის ძრავა`, `დამფუძნებელი
  პრინციპი` (want `ფუძემდებლური`), "one dictionary away".
- **`მონიტორინგი` connotes surveillance** — never for a
  privacy-first product's own tracking feature.
- **Two adverbials of time must not stack**; the frame fronts
  (`ცვლის განმავლობაში რეალურ დროში აწვდის …`).
- **Typography and numbers.** Georgian quotes are „ “ — a text that
  opens with „ and closes with ASCII " is a visible defect. No comma
  as a thousands separator.

An anonymity claim is not a wording question: full anonymity belongs
to crowding only, and a Georgian span asserting it more broadly goes
to architect-cto, not into a translation fix.

*References: georgian-review-gate*

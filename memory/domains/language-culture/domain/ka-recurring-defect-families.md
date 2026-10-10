---
role: "language-culture"
class: domain
topic: "ka-recurring-defect-families"
description: The Georgian defect families that recur across every gzapi surface — check these first before reading a new text line by line
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 3789e111f1ed1709
---

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
- **Attribution to the person.** On a screen where the text sits beside
  someone's name — the driver registry above all — a participle or a
  possessive attaches to the HUMAN and reads as a verdict on them
  rather than a state of their record. Three instances on that one
  screen: „სახელი ჯერ არ აქვს" said the driver has no name where
  en-US said the record does (ad0cef3c, fixed c68b9fb1); „მძღოლის
  ჩანაწერი არ არსებობს" was false because the driver DOES have a
  registry row and only the identity record is missing (fixed before
  delivery, af9f11a4); „უარყოფილი" as a status badge made a rejected
  person out of a refused application (retracted in delivery,
  2026-09-20 — „არ დამტკიცდა"). The fix is always the same shape: name
  what the sentence is about, or use an impersonal form. Russian
  reaches the same answer by making the application states impersonal
  and leaving the record states agreeing.

- **Typography and numbers.** Georgian quotes are „ “ — a text that
  opens with „ and closes with ASCII " is a visible defect. No comma
  as a thousands separator.

An anonymity claim is not a wording question: full anonymity belongs
to crowding only, and a Georgian span asserting it more broadly goes
to architect-cto, not into a translation fix.

*References: georgian-review-gate*

*Observed 2026-09-20 (language-culture)*

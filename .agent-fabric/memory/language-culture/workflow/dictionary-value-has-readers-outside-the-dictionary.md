---
role: "language-culture"
class: workflow
topic: "dictionary-value-has-readers-outside-the-dictionary"
description: before changing or renaming a dictionary value or a UI term, find every reader of the old text — tests, comments, other values that quote it — and sweep by concept, not by string
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e9a15fde6344732f
---

## before changing or renaming a dictionary value or a UI term, find every reader of the old text — tests, comments, other values that quote it — and sweep by concept, not by string

A value in a locale dictionary is read by more than the screen that shows it. When you change one, the old text is still in these places:
- **Tests that assert the literal text** through the real dictionary. Some import the JSON file directly. Others import it through a wrapper module (for example a `dictionaries.ts` that bundles the JSON). A search for importers of the JSON file finds only the first kind; the blind review of gzapp#1099 found the second kind (status_web `StatusPage.test.tsx`, "Day colours"). Search for the **old text itself**, across all files.
- **Tests that assert a fallback template's output**, which fail when the real copy replaces the placeholder (gzapp#1115, `FeasibilityHead.test.tsx`).
- **Code comments that quote the sentence** (gzapp#1099 review F3, two passenger_flutter comments). The fix that does not go stale is a comment that names the key, not the sentence.
- **Other values that quote it**, such as a button label quoted in a hint and in an error. These change in every locale, so tell each locale holder.

When a term changes (a step is renamed, a "restriction" becomes a "zone"), sweep for the **concept** on the same screen and in its error keys, not for the old label string. A sweep by string missed the old step's words in five other values (0deacbb08, then 51b41640e). Without a sweep, a badge and its error name one thing in two ways (4457720b0).

**Why:** each of these readers sits in another owner's lane. A miss shows up only as a red suite or a review finding after the copy has been delivered.

**How to apply:** before you deliver a changed value, run a full-text search for the old text and its concept words. List each hit by owner. Ask the owner of each test or comment for a supplier commit, in the same delivery.

Related: [[key-value-true-in-every-state]]

*References: key-value-true-in-every-state*

*Observed 2026-10-15 (language-culture)*

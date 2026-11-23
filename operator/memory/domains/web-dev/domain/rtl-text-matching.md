---
role: "web-dev"
class: domain
description: "React Testing Library's getByText cannot match a sentence split across sibling DOM nodes"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-8a543ee5423d427c"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 0b8f0aa407f20135
  - fa64121be01b8e55
  - fe1ad5460ec3e78c
---

## React Testing Library's getByText cannot match a sentence split across sibling DOM nodes

Testing Library's `getByText`/`getByRole` text matchers only match a single element's own `textContent`. As soon as part of a sentence is wrapped in a child element (e.g. an accessible `<time>` element embedded inside a translated sentence, as a timestamp component embedded in translated copy does), a regex or string match against the full sentence throws 'unable to find element' even though the sentence renders correctly on screen. This recurred across several rounds of a status page's timestamp work whenever timestamps moved from a flat string into semantic markup. The durable fix is a helper that walks `document.body.querySelectorAll('*')` and matches on each element's own `textContent`, returning the innermost matching element (and a `noSentence()` negative counterpart) — not a workaround specific to any one component.

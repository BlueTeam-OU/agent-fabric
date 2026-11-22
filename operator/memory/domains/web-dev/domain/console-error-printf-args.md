---
role: "web-dev"
class: domain
description: "React's console.error calls pass a printf-style template plus separate substitution arguments, not an interpolated string"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-948c9fcd4da94057"
    host: "develop-qzapp"
derived_from:
  - 6032d2409f829785
  - 7a83a0cc9d1e3b59
  - f85686ff63156a75
---

## React's console.error calls pass a printf-style template plus separate substitution arguments, not an interpolated string

React logs warnings like the 'unrecognized tag' warning for a custom/new HTML element as `console.error("The tag <%s> is unrecognized in this browser", tagName)` — the first argument is the literal template containing `%s`, and the tag name is a separate second argument. A console filter written to match the *rendered* sentence (`/The tag <search> is unrecognized/`) will never match, because `args[0]` is always the unsubstituted template. A correct filter must match the template shape against `args[0]` and check the substitution value(s) in the later `args` positions. This is a general fact about how React's internal warning machinery calls `console.error`, independent of which specific warning is being filtered.

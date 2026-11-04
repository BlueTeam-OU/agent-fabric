---
role: "web-dev"
class: domain
topic: "axe-under-jsdom-and-state-markers"
description: "axe in jsdom answers landmark-one-main / page-has-heading-one \"incomplete\" even for correct markup; a state audit needs a marker only that state renders, checked absent in the others"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - ea5950fa45733956
---

## axe in jsdom answers landmark-one-main / page-has-heading-one "incomplete" even for correct markup; a state audit needs a marker only that state renders, checked absent in the others

axe-core under jsdom returns `landmark-one-main` and `page-has-heading-one` as **incomplete** whatever the markup (measured with a correct `<main><h1>`): both decide visibility from layout. A suite that fails only on `violations` silently never holds them. `@gzapp/web-shared/testing/axe` reads both off the DOM itself in page scope, and refuses page scope on an element root. Its icon-ligature probe also calls `canvas.getContext`, which jsdom logs as not implemented; stub it only for the run.

A per-state audit (loading / empty / loaded / error) proves nothing about the state its label names unless:
- the fixture really varies by shape (a read that ignored `shape` made "empty" audit the loaded table);
- each loaded state waits for a marker only the rows draw;
- the empty state asserts that marker absent.

"fp-1" from an envelope, and a word from the page description, both passed in empty.

**Why:** the blind review of gzapp #1161 found both (F1, F2) after the suite had been green three runs in a row.

**How to apply:** for any multi-state test, add the negative check in the other states; a marker that appears in both is not a marker. Related: [[await-what-only-the-target-state-renders]], [[a-test-client-unlike-production-hides-the-bug]].

*References: a-test-client-unlike-production-hides-the-bug, await-what-only-the-target-state-renders*

*Observed 2026-10-25 (web-dev)*

---
role: "web-dev"
class: domain
topic: "nested-strictmode-does-not-double-effects"
description: "React 19 does not double-invoke effects of a StrictMode nested inside a tree mounting in the same render — a StrictMode-guard test must put it at the root"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 89f02d88167cba21
---

## React 19 does not double-invoke effects of a StrictMode nested inside a tree mounting in the same render — a StrictMode-guard test must put it at the root

Measured 2026-10-19 in apps/operator_web (React 19, vitest/jsdom), a
useEffect counter per placement:

- `render(<StrictMode><C/></StrictMode>)` → 2 runs
- `render(<div><StrictMode><C/></StrictMode></div>)` → 1 run
- StrictMode subtree mounted later by a state change → 2 runs

So a test that wraps the component in StrictMode *inside* its providers
passes with the guard (`if (ranRef.current) return;`) deleted —
operator_web CallbackPage.test.tsx did, until StrictMode moved outside
QueryClientProvider/I18nProvider, as main.tsx mounts it (commit on
develop-qzapp/web-dev-02/feat/j14-…). Checked the repo's other StrictMode
tests then: admin_web driver-applications (root) and web-shared
confirm-toast (late mount) are real.

**How to apply:** put StrictMode at the root of the rendered tree, and
mutation-check the guard. See [[revert-test-reads-the-exit-not-the-tally]].

*References: revert-test-reads-the-exit-not-the-tally*

*Observed 2026-10-19 (web-dev)*

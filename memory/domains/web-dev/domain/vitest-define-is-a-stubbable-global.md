---
role: "web-dev"
class: domain
topic: "vitest-define-is-a-stubbable-global"
description: "A Vite `define` constant is a live global under vitest — vi.stubGlobal changes it per test; a production build replaces it statically."
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 235f75c65dfe0ebd
---

## A Vite `define` constant is a live global under vitest — vi.stubGlobal changes it per test; a production build replaces it statically.

Under vitest (5.0.5, measured 2026-11-10 in packages/web-shared), a key in the
config's `define` is readable as `globalThis.<KEY>`, and assigning it, or
`vi.stubGlobal("<KEY>", …)`, changes what code that reads the bare identifier
sees in that test. `typeof <KEY>` guards a missing define. So a build-time stamp
read by shared code needs no prop or test-only seam in production: a suite that
needs another value stubs the global and `vi.unstubAllGlobals()` in afterEach.
Used for `__GZAPP_I18N_BASELINE__` (web-shared `src/i18n/baseline.ts`,
date-picker.test.tsx stamps its synthetic `xx-Fake` locale this way), commit
8f06e10dc on the j47 branch.

Also measured 2026-11-10: `vitest run --disable-console-intercept <path>` runs
the WHOLE suite — the flag takes the first path as its value, so the filter
is gone (a two-path run collected only the second file). Put the paths first:
`vitest run <paths…> --disable-console-intercept`. Under host load a whole
admin_web run took 14 min and died on worker-start timeouts.

*Observed 2026-11-10 (web-dev)*

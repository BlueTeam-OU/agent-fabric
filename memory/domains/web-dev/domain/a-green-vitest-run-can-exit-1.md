---
role: "web-dev"
class: domain
topic: "a-green-vitest-run-can-exit-1"
description: "Vitest run exits 1 with every test passing: read the 'Errors N error' line; a timer a provider never clears fires after jsdom teardown"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 00c6e8eae2090cca
---

## Vitest run exits 1 with every test passing: read the 'Errors N error' line; a timer a provider never clears fires after jsdom teardown

A Vitest run can report every file and test passed and still exit 1, with
`Errors  1 error` under the tally and an "Unhandled Errors" block above it.
The error is charged to whichever file was running, not to the code that
caused it. Seen 2026-10-27 on gzapp advertiser_web: `ReferenceError: window
is not defined` from react-dom's `dispatchSetState`, attributed to
revisionDuplicate.test.tsx. The cause was in web-shared's ToastProvider: a
success toast's 4.5 s `setTimeout` was never cleared on unmount, so under
host load it fired after that file's jsdom was gone. The file passed alone
3/3, which is the signature of the problem. Fixed in fcd28a27c (gzapp #1187):
timers are tracked in a ref and cleared in an effect cleanup, and the test
asserts `vi.getTimerCount()` is 0 after unmount, which fails with the
cleanup removed.

How to apply: judge a suite by its exit code and the Errors line, never by
the tally alone. When an unhandled error names a file, grep the stack for a
shared component's timer or subscription before suspecting that file. Related:
[[revert-test-reads-the-exit-not-the-tally]].

*References: revert-test-reads-the-exit-not-the-tally*

*Observed 2026-10-27 (web-dev)*

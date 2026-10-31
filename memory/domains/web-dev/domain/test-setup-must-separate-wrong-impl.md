---
role: "web-dev"
class: domain
topic: "test-setup-must-separate-wrong-impl"
description: "Why a test that survives a revert can still miss the scenario it names: the setup lets the wrong implementation pass too"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7d32f6e2d4f9f850
---

## Why a test that survives a revert can still miss the scenario it names: the setup lets the wrong implementation pass too

A test can fail when you delete the behaviour and still not cover the
scenario it names. That happens when the test setup lets the wrong
implementation produce the same output. Before trusting a test, ask: would
the plausible wrong version behave differently under this fixture and this
assertion? Four ways it went wrong in one week:

- **Test defaults differ from production.** The test QueryClient used
  staleTime 0 while production used 30s. Every key switch refetched, so the
  cache-replay bug the test named could not happen in the harness. Build the
  test client from production's defaults.
- **The test asserts the request, not the display.** "A second request goes
  out" also passes with staleTime 0 alone, while the cached page is still on
  screen. Hold the response open with an unresolved promise and assert what
  the person sees while the request is in flight.
- **The test asserts only an absence.** "No row is rendered" passes against
  a blank card as well as against the loading skeleton. Also assert the
  state that should be there (the loading placeholder and its status label).
- **The fixture's sources agree.** An elapsed-time test whose fixture has
  the server's elapsed time equal to the device's also passes with the
  wall-clock form. Make the two differ, and move the monotonic clock while
  the wall clock stays put.

**Why:** each of these was green, and each passed a revert test of the most
obvious change, while the defect it named was still shipping.

**How to apply:** for every test that guards a behaviour, name the wrong
implementation someone would most plausibly write, and change the fixture
or assertion until that version fails. Deleting the behaviour is necessary
but not enough.

Sources (GZCoord): 01a0c232-f716-717b-8618-5fe5473c6f08,
01a0c23b-d1a5-772b-8408-ddfdf25cd4e4, 01a0c23e-12d7-7159-b005-4b6fd6ecd365,
01a0bab1-0da8-7d97-999c-eddf0a3d46ab. Related: [[tanstack-staletime-vs-gctime]].

*References: tanstack-staletime-vs-gctime*

*Observed 2026-10-18 (web-dev)*

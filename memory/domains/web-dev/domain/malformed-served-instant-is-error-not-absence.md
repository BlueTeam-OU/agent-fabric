---
role: "web-dev"
class: domain
topic: "malformed-served-instant-is-error-not-absence"
description: "A served date/time that does not parse: how NaN slips through comparisons, clamps and Intl into 'Down for NaN d', and what to render instead"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ef4fc7efcbfe8108
---

## A served date/time that does not parse: how NaN slips through comparisons, clamps and Intl into 'Down for NaN d', and what to render instead

`Date.parse` of a malformed instant is `NaN`. Every check after that is
silently wrong. Every comparison with NaN is false, so a chain of
`if (s < 60) … else if (s < 3600) …` falls through to its last branch.
`Math.max(0, NaN)` is `NaN`, so the clamp catches nothing. And
`Intl.NumberFormat(...).format(NaN)` is the string "NaN". The result is a
plausible sentence on the page: "Down for NaN d", or "Lasted NaN d". A
grouping step that runs over the instants can also take the whole page
down.

What to do: detect the parse failure where the served value enters the
client, and return a distinct *malformed* outcome. Do NOT return
null/absent: that would file a contract breach under a state the contract
allows, and the page would say nothing where it should say that something
is wrong. Keep whatever is still readable (the component's state), drop the
derived phrase, and show a sentence that says the response could not be
read. It is not the "no data" text, which is a claim about the world. Test
it with a malformed fixture that asserts the error rendering and asserts
"NaN" appears nowhere in the DOM. The second assertion is the one that
catches this.

**Why:** found twice on gzapp's public status page (an elapsed phrase, and
later an incident's duration). architect-cto ruled it is the same breach as
a required value that never arrived (gzapp ADR-017 rule 16).

**How to apply:** treat every served instant like an unknown enum value
([[unknown-served-enum-renders-unknown]]): validate at the wire boundary,
but render a malformed value as an error, never as absence.

Sources (GZCoord): 01a0bd7e-6910-756d-adf1-7a7329848234,
01a0bd7f-2844-732b-b95f-9a14f0817c08, 01a0be12-ff85-7591-bd27-b19333e81691,
01a0be14-2b3a-7d58-ad49-f83d56994380. In the tree: gzapp
apps/status_web/src/features/status/StatusPage.test.tsx ("NaN" assertions),
origin/main 7392f0a17.

*References: unknown-served-enum-renders-unknown*

*Observed 2026-10-18 (web-dev)*

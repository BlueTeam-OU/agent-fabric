---
role: "flutter-dev"
class: domain
topic: "contract-closure-unevaluatedproperties"
description: To tell whether a gzapp contract closes an object, check unevaluatedProperties — additionalProperties alone is wrong wherever the schema uses $ref.
tier: 2
knowledge_scope: full
distilled_at: "2026-09-28"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 301af98f5e02e49e
  - 7c1ec8c0b9816689
---

## To tell whether a gzapp contract closes an object, check unevaluatedProperties — additionalProperties alone is wrong wherever the schema uses $ref.

**`additionalProperties` does NOT tell you whether a gzapp contract
closes an object.** These schemas are JSON Schema 2020-12 and compose
with `$ref`; `additionalProperties` cannot see through a `$ref`, so a
schema that refs another and wants to close writes
**`unevaluatedProperties: false`** instead — and leaves
`additionalProperties` unset.

Concretely (`contracts/journey/journey-plan-request.schema.2.0.0.json`):

```json
"origin": {
  "type": "object",
  "$ref": "urn:gzapp:schemas:common:place",
  "unevaluatedProperties": false
}
```

`additionalProperties` is unset there, and `common/place.schema.json`
also leaves it unset — so a check that reads only `additionalProperties`
concludes "open" for both, and is **wrong**: the carrier closes the
place, and has since 2.0.0.

I made exactly that mistake on 2026-09-17 while checking the passenger
against #827 (unknown request keys become 400). I concluded the echoed
place was open and warned backend-dev-01 that closing `common:place`
later would turn their own geocode output into a 400 on the next plan
request. backend-dev-01 corrected it: already closed at the carrier, and
in any case the backend has ONE `Place` record serving both directions,
so a key added is served and accepted in the same commit.

**So when judging closure:** read `unevaluatedProperties` first wherever
there is a `$ref`, `allOf`, `anyOf` or `oneOf`; `additionalProperties`
only decides for a flat schema that composes with nothing.

Second, smaller trap from the same check: **resolve a contract by
`x-contract.status`, not by filename.** I read
`journey-plan-request.schema.json` (status `retired`, origin
`{lat,lng}`, closed) and briefly concluded the passenger was about to
400 on every journey plan. The active one is
`journey-plan-request.schema.2.0.0.json` (status `active`), which refs
`common:place`. The bare name is the OLD contract.

Related: [[verify-against-the-artifact]].

### The nuance that stopped me raising a false finding (2026-09-19)

`additionalProperties: false` fails to close a schema **only when the
properties it must judge arrive from elsewhere** — a sibling `$ref` or
`allOf` branch that introduces properties the keyword cannot see.

It still closes when the REFERENCED schema closes itself. Measured on
`journey-state` 1.2.0, whose `replacement_plan` is
`allOf: [$ref journey-plan-response, {properties: {plan_kind: const}}]`
with no closure key of its own:

| instance | result |
|---|---|
| the repo's own valid fixture (control) | ACCEPTED |
| an undeclared member INSIDE `replacement_plan` | **REJECTED** |
| a misspelled top-level `replacment_plan` | **REJECTED** |

It closes because `journey-plan-response` carries
`additionalProperties: false` on its own object, and the `allOf` branch
introduces no new property (`plan_kind` is already declared there).

**Confirmed against the pipeline's own validator**, not just mine:
backend-dev-02 re-ran the same three cases through Ajv 2020 (what
`tools/validate_contracts/validate.js` runs), every contract loaded by
`$id`, and got the same three answers. So the two implementations agree
about `allOf` closure here and this is the pipeline's behaviour, not one
library's reading.

So: check where the properties are DECLARED before calling a composed
schema open. I nearly reported a second blind side to backend-dev-02
on the strength of the general rule alone.

*References: verify-against-the-artifact*

*Observed 2026-09-19 (flutter-dev)*

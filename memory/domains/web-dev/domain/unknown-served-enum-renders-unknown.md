---
role: "web-dev"
class: domain
topic: "unknown-served-enum-renders-unknown"
description: "What a screen shows when the server sends a status, role or model value the client's closed set does not have yet"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 048b549c6204b5d2
---

## What a screen shows when the server sends a status, role or model value the client's closed set does not have yet

The server can add a value to an enum it serves (a status, a role, a model)
before the client knows about it. The screen shows such a value as "unknown".
It never shows the raw key, a blank or a crash. The type is widened where the
wire value enters the client, so the closed-key tables behind it stay closed and
keep their strict index typing. The "unknown" label is a locale key like any
other text. Landed in gzapi-org/gzapp#1106 (operator_web) and #1108 (admin_web,
advertiser_web). I proposed it for the web-dev brief on 2026-10-17 (GZCoord
REPLY 01a1486b-e7a3).

**Why:** a release that adds a value on the server first must not break the
screens of a client that has not shipped the new value yet.

**How to apply:** for any enum the client renders from the wire, widen at the
boundary and map unknown values to the "unknown" key. Do not add a fallback
inside the closed table; under strict index access it is dead code.

*Observed 2026-10-17 (web-dev)*

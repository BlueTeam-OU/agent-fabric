---
role: "p2p-network-dev"
class: domain
topic: "domain-stand-in-holds-the-seams-shape"
description: "a host stand-in for a device runner must enforce the device seam's value shape at its one funnel, for every case, or shape bugs show only on a phone"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 77c0b81539ec02db
---

## a host stand-in for a device runner must enforce the device seam's value shape at its one funnel, for every case, or shape bugs show only on a phone

A device runner can flatten what it returns: Android instrumentation `putString`s every
result value, so an array or object reaches the host as text. A host stand-in that passes
values through unchanged diverges from the phone in silence. The first instance,
`keys::SENT`, was fixed in 060dc971, and the all-strings assertion went into human_chat.rs
only. The next instance, `PRIVATE_DIRS` in trust_boundary, was then found on a phone,
because nothing on the host refuses a structured value.

**Why:** fixing the shape per key, or asserting it in one case's test, fixes one instance
of a class. The seam's rule ("every value is text") belongs in the one function every
case's result passes through on the host, which in InterWeave is `CaseRun::result` in
tests/android-e2e/src/lib.rs.

**How to apply:** when a stand-in replaces a device or process seam, list what that seam
does to values (stringifies, truncates, drops keys) and enforce each rule in the
stand-in's funnel, with a negative test beside a passing control. InterWeave work is j36.
See [[domain-device-tests-run-in-the-app-process]].

*References: domain-device-tests-run-in-the-app-process*

*Observed 2026-10-16 (p2p-network-dev)*

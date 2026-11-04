---
role: "web-dev"
class: domain
topic: "popup-session-not-keyed-to-click-state"
description: "a per-act object whose window a click opens must not be re-created by the state that same click sets — the swap drops the window it just opened"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 75042c63144f9c5e
---

## a per-act object whose window a click opens must not be re-created by the state that same click sets — the swap drops the window it just opened

In gzapp #1152 I first keyed the step-up session to the reason-for-access
(`useStepUp(reason)`). The ReasonGate submit calls `verify()` (the popup needs the click) and
then `setReason()`. The re-render swapped in a NEW session, and the effect cleanup dropped the
old one, aborting the popup it had just opened. The jsdom stubs hid it; I caught it on reading.
**Why:** a user-gesture side effect has to land on the object that will still exist after the
re-render the same click triggers.
**How to apply:** keep the object for the component's life and start a new act in place
(`session.begin()` = drop + verify, inside the click), not by changing a key. Related:
[[keycloak-stepup-acr-values-alone]]

*References: keycloak-stepup-acr-values-alone*

*Observed 2026-10-20 (web-dev)*

---
role: "web-dev"
class: domain
topic: "lock-on-what-this-component-submitted"
description: "A UI lock derived from a shared session's status alone misfires when the component remounts over it or its draft drifts; key the lock on the value THIS component submitted, and clear it on the explicit release."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - ce3d50bb829ecec8
---

## A UI lock derived from a shared session's status alone misfires when the component remounts over it or its draft drifts; key the lock on the value THIS component submitted, and clear it on the explicit release.

admin_web's reason lock (#1153, architect-cto decision 01a1597d) first
read `isReasonLocked(session status)` in ReasonGate. The blind review
found two misfires with one root:

- the positions popover's Retry remounts the gate over a session still
  `verified`, so a fresh, empty gate opened locked, its hint claiming a
  reason was covered;
- after Change reason, a draft re-verified from the prompt (for reads
  still keyed on the submitted reason) was shown locked as if covered.

Fix: the gate keeps `submitted` and locks only while the status holds
AND `draft === submitted`; Change reason also sets `submitted = null`,
or a draft retyped through the old text re-locks mid-word (round 3).

The general rule: a session (token, subscription, lease) outlives the
component that displays it, so "is something held?" is the wrong
question for a field. Ask "is what is held for what THIS field shows,
by THIS instance's own act?" And on any surface where a write carries
the value in its body, a waiting write must hold the lock too, and the
release must abandon it (`drop()`), not merely forget the token.

See also [[keeps-it-on-screen-means-node-identity]].

*References: keeps-it-on-screen-means-node-identity*

*Observed 2026-10-20 (web-dev)*

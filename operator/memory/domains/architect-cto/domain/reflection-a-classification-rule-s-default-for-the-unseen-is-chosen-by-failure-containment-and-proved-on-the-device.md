---
role: "architect-cto"
class: domain
topic: "reflection-a-classification-rule-s-default-for-the-unseen-is-chosen-by-failure-containment-and-proved-on-the-device"
description: "W44 - a rule keyed on a classifier has a second case, what the classifier never sees: ADR-0052 rule 10's 'unclassified counts as local' default let a phone's background cellular and IMS addresses pass all four surfaces because the…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-01"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 741f3de1a1ca7ee8
---

## W44 - a rule keyed on a classifier has a second case, what the classifier never sees: ADR-0052 rule 10's 'unclassified counts as local' default let a phone's background cellular and IMS addresses pass all four surfaces because the platform never reported those networks; the default for the unseen is chosen by which wrong side costs more, and the gate passes only on a device row with the real platform

2026-10-26 I ruled rule 10 as a classification by transport (a
carrier's network is no local network) with "a transport the bridge
cannot classify counts as local - the behaviour before the rule".
2026-10-27 the Pixel 9a failed gate (e): Show listed both carrier
10.x/32 addresses. The bridge's listen (INTERNET) never reported the
background cellular network (no FOREGROUND behind validated Wi-Fi) or
the IMS network (restricted), so the view held Wi-Fi only, and the
runtime classifies only what the view names; the bound set then
passed Show, Identify, the DCUtR offer sites and rule 3's own-listener
test. On mobile data alone the unviewed IMS address counted as an own
private listener, admitting a far end's private candidate into the
carrier's network: the probe rule 10 exists to refuse. Ruled (b): a
private address this host binds that a present view does not hold is
on no local network. Wrongly hiding costs a hotspot host's address
(the pair still connects one way); wrongly showing costs the probe
and the carrier address handed to every Identify peer. The hotspot
case then had its own cause (reported only from target SDK 37).

**Why:** "behaviour before the rule" is not a reason; the unseen case
is the common one on a phone (two of three networks were never
reported), and the model of the platform is not the platform.

**How to apply:** when ruling a classification, write the row for
"the classifier reports nothing" and choose its default by failure
containment (which wrong side is the security side); name the device
row that proves each case, and the record says the gate passes only
on that row's re-run; when a widened read is part of the fix, measure
whether it mattered (the no-uplink Wi-Fi already carried INTERNET, so
the widening admitted nothing there). Related:
[[reflection-engine-behaviour-clause-is-decided-by-a-run-with-a-control]],
[[adr-0052-rule-10-outside-the-view-2026-10-27]].

*References: adr-0052-rule-10-outside-the-view-2026-10-27, reflection-engine-behaviour-clause-is-decided-by-a-run-with-a-control*

*Observed 2026-10-31 (architect-cto)*

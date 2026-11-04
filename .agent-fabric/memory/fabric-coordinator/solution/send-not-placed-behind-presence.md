---
role: "fabric-coordinator"
class: solution
topic: "send-not-placed-behind-presence"
description: "why gzcoord-send let a role-named TO through — the not-placed test lives inside the presence ask, and --force overrides it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fb070af973bc8d9e
---

## why gzcoord-send let a role-named TO through — the not-placed test lives inside the presence ask, and --force overrides it

On main 3abb7669, presence.py check_addressees answers "not-placed" for a TO
no host places (e.g. develop-qzapp/fabric-coordinator), but send.py only reaches
it through the relay-backed presence call: a skipped presence (token refused)
passes, a dry run never checks, and --force overrides not-placed exactly like
offline. architect-cto-01's REQUEST 01a15f3e (2026-10-21) was lost that way.
Contract to python-dev-03 in REQUEST 01a182be (j394, 2026-10-28): local
placement test before presence; a role slug in TO refused exit 2 even with
--force; compose --to the same. 2026-10-30: I supplied the five en-US.json keys
(5416e007) and the skill §3 text (76e936d7) as commits on python-dev-03's
branch develop-qzapp/python-dev-03/feat/j95-gzcoord-send-a-to-naming-no
itself, rather than waiting for a merge: the rule and its docs land in one
PR. ka-GE/ru-RU come from the language-culture holders on that branch. See [[verify-sends-in-journal]].

*References: verify-sends-in-journal*

*Anchors: `tools/fabric/control/presence.py::not-placed`, `tools/fabric/gzcoord/send.py::send.presence-forced`*

*Observed 2026-10-28 (fabric-coordinator)*

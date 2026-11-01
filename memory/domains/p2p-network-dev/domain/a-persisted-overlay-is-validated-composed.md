---
role: "p2p-network-dev"
class: domain
topic: "a-persisted-overlay-is-validated-composed"
description: "A runtime change persisted as an overlay over a validated config file must be judged as the next start will judge the COMPOSED profile: refuse at set time what the next start would refuse, fail the start loudly naming the overlay, never…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 87177a2068f7ecdb
---

## A runtime change persisted as an overlay over a validated config file must be judged as the next start will judge the COMPOSED profile: refuse at set time what the next start would refuse, fail the start loudly naming the overlay, never normalise or read an untrusted overlay away

InterWeave persists operator changes made over admin IPC as overlay files
beside config.yaml (trust, availability, endpoints; ADR-0028). config.yaml
is validated on its own, but the runtime runs the composition. The same
gap came up for each of the three overlays:

- **Trust** (#216 F2): an allow that the running bound admits, made while
  an earlier failed write had left the overlay ahead of the runtime, would
  put the overlay past MAX_ALLOWED_PEERS at the next start. Ruled: refused
  at set time (InvalidArgument), nothing written, "an ahead state never
  grows into a fatal start".
- **Availability** (j55): a present overlay that cannot be trusted (not
  owner-only, wrong shape) REFUSES the start. Reading it as absent would
  silently revoke the person's opt-in.
- **Endpoints** (#261 F1): validation rules that read the ENABLED set
  (TooManyAdvertised, AndroidEndpointNotEnabled) passed config.yaml alone
  and failed the composed profile. The ADR's "no analogue of the bound"
  was false. Ruled: validate the composition at set time as the start
  does; at start, a conflict is FATAL and names the overlay and the rule.
  Never normalise it away, because dropping entries until the profile
  validates chooses for the operator.

**How to apply:** for any persisted override of a validated document,
list every validation rule that reads a field the override can change, and
run the same validator on the composed result at both doors: the set (to
refuse) and the load (to fail by name). A present-but-untrusted override
fails closed and loud; only an ABSENT file means "no override". Test with a
config that validates alone and an overlay that breaks it composed. Related:
[[a-paused-consumer-on-a-shared-stream-stalls-its-own-calls]] for the other
"unknown is not absent" rule.

*References: a-paused-consumer-on-a-shared-stream-stalls-its-own-calls*

*Observed 2026-10-25 (p2p-network-dev)*

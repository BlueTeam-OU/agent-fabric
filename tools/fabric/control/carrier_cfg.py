"""tools/fabric/control/carrier_cfg.py — the three values of runtime/control/config.json `control_carrier`
(ADR-029 rule 18) and the two questions every caller of the control plane asks of one: is the second carrier used,
and is the relay used. One place, so a fourth caller cannot read "dual" as the only value that names the second carrier.

  relay        the relay alone; the default and what an absent key means
  dual         the relay (the record) and the second carrier beside it; either may answer
  <SECOND_ONLY> the second carrier alone (the carrier package's own name, which a generic file does not spell): control neither polls nor posts to the relay's control channel, and an op that
               cannot ride it goes through hostexec: an action (control_link.CARRIER_ACTION_OPS) always, the carrier's own read
               (the rest of control_link.RELAY_ONLY_OPS) only for an account the carrier did not answer (ADR-064 rule 14)
"""
from __future__ import annotations

from gzcoord.carrier import CARRIER_NAME

# The carrier package spells its own name; lint's project-name rule keeps it out of every generic file, this one included.
SECOND_ONLY = CARRIER_NAME
RELAY, DUAL = "relay", "dual"
CARRIERS = (RELAY, DUAL, SECOND_ONLY)


def uses_second_carrier(cfg: dict) -> bool:
    return cfg.get("control_carrier") in (DUAL, SECOND_ONLY)


def uses_relay(cfg: dict) -> bool:
    return cfg.get("control_carrier") != SECOND_ONLY

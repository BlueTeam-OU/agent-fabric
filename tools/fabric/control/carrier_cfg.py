"""tools/fabric/control/carrier_cfg.py — the three values of runtime/control/config.json `control_carrier`
(ADR-029 rule 18) and the two questions every caller of the control plane asks of one: is the second carrier used,
and is the relay used. One place, so a fourth caller cannot read "dual" as the only value that names InterWeave.

  relay        the relay alone; the default and what an absent key means
  dual         the relay (the record) and InterWeave beside it; either may answer
  interweave   InterWeave alone: control neither polls nor posts to the relay's control channel, and an op that
               cannot ride InterWeave (control_link.RELAY_ONLY_OPS, ADR-064 rule 14) goes through hostexec
"""
from __future__ import annotations

RELAY, DUAL, INTERWEAVE = "relay", "dual", "interweave"
CARRIERS = (RELAY, DUAL, INTERWEAVE)


def uses_second_carrier(cfg: dict) -> bool:
    return cfg.get("control_carrier") in (DUAL, INTERWEAVE)


def uses_relay(cfg: dict) -> bool:
    return cfg.get("control_carrier") != INTERWEAVE

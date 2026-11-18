---
role: "devex-tooling"
class: solution
topic: "arm-grant-carrier-row-verified-sender"
description: "How fabric-pr arm judges a WAIVES/AUTHORIZES grant the journal (not the relay) answered — carrier vs sender_verified, and how to test it end to end"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b1c60f405b05a678
---

## How fabric-pr arm judges a WAIVES/AUTHORIZES grant the journal (not the relay) answered — carrier vs sender_verified, and how to test it end to end

Since W4 of the InterWeave-only cutover (commit 4be37347, branch develop-qzapp/devex-tooling/for/user/w4-arm-journal-grant,
the owner's D4 2026-11-13), verify_grant in tools/fabric/github/arm.py reads `gzcoord-inbox --replay <id> --json`
journal-first (W3, #581). A row whose `carrier` is not `claude-bridge` counts only with `sender_verified is True` and
that sender == FROM; a relay row (carrier claude-bridge, or no carrier field = pre-W3 inbox) is judged as before.
`carrier` is the FIRST carrier, so a relay row a carrier verified later stays a relay row.

arm does not import the relay name (arm import closure, see [[arm-import-closure-needs-boundary-hunk]]):
arm.RELAY_CARRIER is pinned in test_arm_cli against inbox_parts.records.RELAY_CARRIER and episodic.DEFAULT_CARRIER.

End-to-end pattern in test_arm_cli: test_gzcoord_carrier_inbox.World([]) for the account env, episodic.inbound(...,
carrier="interweave") with os.environ swapped to w.env, w.stub.close() (relay refuses), then cli() with
AGENT_FABRIC_GZCOORD_INBOX=P.INBOX_CMD, AGENT_FABRIC_PR_SESSION=C.ME, only the account keys of w.env (w.env copies the
session's AGENT_FABRIC_*), PR branch f"{C.ME}/feat/x"; rmtree P.SCRATCH after. Exit-2 wording is now "could not be read
from the journal or the relay" (test_arm_policy asserts it too).

*References: arm-import-closure-needs-boundary-hunk*

*Anchors: `tools/fabric/github/arm.py::RELAY_CARRIER`, `tools/fabric/github/arm.py::a sender it did not verify`, `tests/test_arm_cli.py::the carrier alone journaled both grants`*

*Observed 2026-11-13 (devex-tooling)*

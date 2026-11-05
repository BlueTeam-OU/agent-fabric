---
role: "fabric-coordinator"
class: threads
topic: "fleetdeck-harness-unit-lock"
description: "For j419's agent-fabric-harness.service: the deck's attach-mode lock lives in /run/user/<uid> else /tmp, so PrivateTmp can split it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 44c3c99a2e305126
---

## For j419's agent-fabric-harness.service: the deck's attach-mode lock lives in /run/user/<uid> else /tmp, so PrivateTmp can split it

The fork side of FleetDeck part 2 is merged: BlueTeam-OU/agent-fabric-fleetdeck#50, at 639271d4 on master, as of 2026-10-28. The deck turns attach mode on only when `moveto --help` lists `--attach`, and that is j419's to add. The interface to match is rust-ui-dev-01's REPLY 01a180eb.

In attach mode, the controller and `start --auto` type into a harness pane only while holding the lock `fabric-deck-harness.<uid>.lock`. The lock lives in /run/user/<uid>, or in /tmp when that directory is missing.

**Why:** if the systemd unit j419 adds runs with PrivateTmp, on a host without /run/user/<uid>, it gets its own /tmp. It would then not share the lock with the deck.

**How to apply:** when writing agent-fabric-harness.service, either set no PrivateTmp, or make sure /run/user/<uid> exists (lingering). Once j419 is on a PR head, rust-ui-dev-01 does the acceptance run: kill one account's attach, check claude keeps working, reattach.

*Observed 2026-10-28 (fabric-coordinator)*

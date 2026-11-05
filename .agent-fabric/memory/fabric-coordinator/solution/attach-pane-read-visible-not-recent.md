---
role: "fabric-coordinator"
class: solution
topic: "attach-pane-read-visible-not-recent"
description: "fleet-deck skips every login with \"never showed moveto's prompt\" — a herdr pane running an attach answers `pane read --source recent` empty; read visible"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0244e4449afb7c32
---

## fleet-deck skips every login with "never showed moveto's prompt" — a herdr pane running an attach answers `pane read --source recent` empty; read visible

2026-10-31, herdr 35a458a0 (#54, attach mode): `fleet-deck start --auto` skipped 29/29 after
PROMPT_WAIT_S (45 s) each, ~21 min. The panes were at "<login> - Enter to activate"; the
attached terminal client redraws the screen, so `herdr pane read <pane> --source recent` is ''
and only `--source visible` holds the prompt. fleet_deck.py DeckFleet.waiting read recent.
Its test passed because the fake herdr returned the prompt for any source — a fake must answer
per argument the way the live binary was measured to (j515, patch on
develop-qzapp/user/fix/j515-fleet-deck-start-auto-skips-all).

Diagnose a whole-fleet skip with the deck's own DeckFleet from a probe script
(read_map, moveto, waiting per login), read-only, before touching units:
the j513 harness_pane enter race is per-pane, never 29/29.

*Anchors: `herdr:fleet-deck/fleet_deck.py::DeckFleet.waiting`*

*Observed 2026-10-31 (fabric-coordinator)*

---
role: "rust-ui-dev"
class: workflow
topic: "deck-recovery-key-classifier-refusal"
description: "Code that makes the herdr deck type /clear and a resume prompt into an agent session after a model safeguard stop is refused by the auto-mode classifier"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9900f7774b266c5b
---

## Code that makes the herdr deck type /clear and a resume prompt into an agent session after a model safeguard stop is refused by the auto-mode classifier

j27 (2026-10-18, REQUEST 01a150b2 from fabric-coordinator): the owner chose
detection + alert + a person-triggered recovery key (agent-fabric PR #300,
commit 423866bb, docs/fleet-deck/tab-states.md). The detection/alert part
landed on herdr branch develop-qzapp/rust-ui-dev-02/feat/j27-safeguard-stop
(8b7a2a4a, 6b8a7529). Writing the recovery key itself (fabric_view.py
`recover`, sending /clear + resume text into the harness pane) was refused
by the Claude Code auto-mode classifier as "Security Weaken", even with the
person's confirmation in the design.

**Why:** a session-side safety check, not a fabric rule; it is not worked
around (different tool, smaller pieces) — the outcome goes to the owner.

**How to apply:** a deck/automation request that types into an agent's
session after a safeguard stop: build detection and alert only, and say up
front that the typing part needs the owner to clear it outside the session
(or hand it to a person to write). See [[diagnosis-evidence-before-cause]].

Outcome: the detection + alert alone merged as fleetdeck #44 (head
93a09966, 2026-10-18), on fabric-coordinator's INFO 01a150c6; the key
waits on the owner. Two lessons from its review rounds: the fork's CI
checks the PR title and every commit subject as Conventional Commits
(scripts/conventional_commits.py), so herdr commits start `feat(fleet-deck):`
/ `fix(…)` / `docs(…)`; and screen-text detection must anchor on the
harness's own glyph block (⎿), stated as an assumption, since agent text
can quote anything.

*References: diagnosis-evidence-before-cause*

*Anchors: `herdr:fleet-deck/fabric_deck.py::SAFEGUARD_MARKS`, `herdr:fleet-deck/fabric_deck.py::_safeguard`*

*Observed 2026-10-18 (rust-ui-dev)*

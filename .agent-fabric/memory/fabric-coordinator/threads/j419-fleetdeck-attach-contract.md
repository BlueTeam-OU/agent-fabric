---
role: "fabric-coordinator"
class: threads
topic: "j419-fleetdeck-attach-contract"
description: "j419 (FleetDeck part 2, agent-fabric side) must match four interface points the fork's PR #50 relies on: moveto --attach token, ssh remote argv 'attach', unit pane's 'Enter to activate' last line, state stream for unit sessions"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 254e5ecaa27beb6e
---

## j419 (FleetDeck part 2, agent-fabric side) must match four interface points the fork's PR #50 relies on: moveto --attach token, ssh remote argv 'attach', unit pane's 'Enter to activate' last line, state stream for unit sessions

On 2026-10-28 rust-ui-dev-01 built FleetDeck part 2's fork side as BlueTeam-OU/agent-fabric-fleetdeck#50 (3 work, 0 fix at the time). It is gated on `moveto --help` listing `--attach`, so it is inert until j419 lands. I chose option A for boot activation: the deck attaches each account only to activate it, then hangs up once the state stream shows a live session and the tab is unfocused. An account that never comes up keeps its attach and is reported. Boot pacing stays in the deck, per [[fleet-boot-auto-order]].

**j419 must match, or the deck breaks:**
1. `moveto <login> --attach`, with `--attach` as a whole token in `moveto --help`.
2. Over ssh the remote command is exactly the one word `attach` (`ssh … <login>@<host> -- attach`). The deck recognises its pane from that argv. This is the ADR-048 §5 rule 4 amendment, plus enter-ssh admitting `attach`.
3. At `--wait`, the unit's pane prints `<login> - Enter to activate` as its last line, as moveto does today; boot presses Enter only at that line.
4. The account's state stream keeps posting for sessions running in the unit; in attach mode the deck's agent row reads only that.

In attach mode, item 5 (`stop --all` through the units) is still mine: the deck hangs up no attach and only says the sessions were stopped through their units.

**How to apply:** when j419 starts, give these four points to the contributor as acceptance, and send rust-ui-dev-01 the PR number at once. Its acceptance (kill an attach, claude keeps working, reattach) and its before/after numbers run against the j419 PR's head.

**Dispatched 2026-10-30.** REQUEST 01a18e65 went to python-dev-03 (idle; python-dev merges its own PR). It covers the harness unit and pane step, install_fleetdeck.py, enter-ssh `attach`, moveto --attach, and fabric-ctl harness-start/stop in units.py, plus tests for points 1-4 and a live check. Mine, as two commits onto its branch: bootstrap.py installs and enables the unit (agentd mechanics), and the ADR-048 §5 rule 4 amendment. Packaging decision: there is no fleetdeck release, so the operator builds and the owner runs `sudo install_fleetdeck.py --from <path>`. A release-asset pin via tools_install comes later. Rollout: the owner runs install_fleetdeck, install_moveto and the ssh-operator enter-ssh step, then `upgrade fabric`, then the deck restarts (stop --all, start --auto). The deck turns to attach mode only at its restart. j419 is blocked on request:01a18e65; re-blocked on job:python-dev-03/j97 (its REPLY 01a18e66) ([[block-on-job-not-request-after-reply]]).

**2026-10-31 ~00:00Z.** python-dev-03 is holding the #435 review for my two commits (QUESTION 01a18f38). I promised them from the next session (REPLY 01a18f39), with a message giving the shas when pushed; after 06:00Z they review the head without them. The commits go onto origin develop-qzapp/python-dev-03/feat/j97-j419-fleetdeck-part-2-agent-fabric, not onto my #437. j444 is parked on job:user/j419.

*References: block-on-job-not-request-after-reply, fleet-boot-auto-order*

*Observed 2026-10-30 (fabric-coordinator)*

---
role: "fabric-coordinator"
class: threads
topic: "j419-harness-on-435"
description: "where FleetDeck part 2's agent-fabric side waits — my two commits ride python-dev-03's #435, then upgrade and the owner's rollout"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d718ae8e858fe73b
---

## where FleetDeck part 2's agent-fabric side waits — my two commits ride python-dev-03's #435, then upgrade and the owner's rollout

2026-10-31: on #435 (python-dev-03's j97 branch, it reviews/arms/merges) I pushed d66d4d04 (bootstrap step 6a'': harness unit installed + enable --now on every account, never restarted — a restart ends the pane's session) and 273e237a (ADR-048 §5 rule 4 amendment, `attach`). REPLY 01a18f52 to python-dev-03. j419 blocked on pr #435. After merge: `fabric-ctl all upgrade fabric`; owner rollout is install_fleetdeck.py, then install_moveto BEFORE the enter-ssh step (an old enter opens a plain shell on --attach); the live read-back (unit starts, attach draws, ssh kill leaves claude, stop = SIGTERM, JSON field names) goes to docs/live-checks/. Local suite red only on sibling corpus lint: [[suite-red-on-sibling-lint]].

2026-10-31 (later session): #435 still OPEN (7 work, 1 fix, 1 merge; guards green, platform-smoke pending). j419 now `fabric-jobs block --on pr:BlueTeam-OU/agent-fabric#435`, so switch will not take it as work until the merge.

2026-10-31 09:15 CET: #435 MERGED 06:55Z (909f686f), #441 (pane process-info --pane fix + shapes live check) merged; fleet all on c6d82919. Unit is installed+enabled on my account, skipped on ConditionPathExists=/usr/local/bin/agent-fabric-fleetdeck (as designed). /usr/local/bin/moveto still the Oct 10 one. REQUEST 01a19106 to rust-ui-dev-01 for a release build (path, fork commit, sha256, --version); j419 blocked on it. Then owner: `sudo python3 tools/fabric/provisioning/install_fleetdeck.py --from <path>` and `sudo runtime/provisioning/moveto/install.sh`, then read back unit/ExecStartPost/enter-ssh attach (what #441 left unverified) into docs/live-checks/.

2026-10-31 08:24Z: REPLY 01a1910f from rust-ui-dev-01: release binary ~/fleetdeck-builds/agent-fabric-fleetdeck-6548d1a8, fork master 6548d1a8, sha256 b27d723f613bb14746af694fa069390c6bdfe24b91b827587dbd0dc7936d36b4, 0.10.0, smoke-tested (attach draws, kill leaves pane). Not hash-checked by me: auto mode refused reading another login's home; the owner checks it at install. Notes: attach errors in a 0x0 pty (read back via ssh -t); the deck needs a restart on fork master + fleetdeck#54 for j167. Next: owner install_fleetdeck --from that path, then moveto install.sh, then my read-back.

*References: suite-red-on-sibling-lint*

*Observed 2026-10-31 (fabric-coordinator)*

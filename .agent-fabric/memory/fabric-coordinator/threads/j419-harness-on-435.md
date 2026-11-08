---
role: "fabric-coordinator"
class: threads
topic: "j419-harness-on-435"
description: "where FleetDeck part 2's agent-fabric side waits — my two commits ride python-dev-03's #435, then upgrade and the owner's rollout"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c8a2249ddc5eed8b
  - d718ae8e858fe73b
  - e219b90014bd40d2
---

## where FleetDeck part 2's agent-fabric side waits — my two commits ride python-dev-03's #435, then upgrade and the owner's rollout

2026-10-31: on #435 (python-dev-03's j97 branch, it reviews/arms/merges) I pushed d66d4d04 (bootstrap step 6a'': harness unit installed + enable --now on every account, never restarted — a restart ends the pane's session) and 273e237a (ADR-048 §5 rule 4 amendment, `attach`). REPLY 01a18f52 to python-dev-03. j419 blocked on pr #435. After merge: `fabric-ctl all upgrade fabric`; owner rollout is install_fleetdeck.py, then install_moveto BEFORE the enter-ssh step (an old enter opens a plain shell on --attach); the live read-back (unit starts, attach draws, ssh kill leaves claude, stop = SIGTERM, JSON field names) goes to docs/live-checks/. Local suite red only on sibling corpus lint: [[suite-red-on-sibling-lint]].

2026-10-31 (later session): #435 still OPEN (7 work, 1 fix, 1 merge; guards green, platform-smoke pending). j419 now `fabric-jobs block --on pr:BlueTeam-OU/agent-fabric#435`, so switch will not take it as work until the merge.

2026-10-31 09:15 CET: #435 MERGED 06:55Z (909f686f), #441 (pane process-info --pane fix + shapes live check) merged; fleet all on c6d82919. Unit is installed+enabled on my account, skipped on ConditionPathExists=/usr/local/bin/agent-fabric-fleetdeck (as designed). /usr/local/bin/moveto still the Oct 10 one. REQUEST 01a19106 to rust-ui-dev-01 for a release build (path, fork commit, sha256, --version); j419 blocked on it. Then owner: `sudo python3 tools/fabric/provisioning/install_fleetdeck.py --from <path>` and `sudo runtime/provisioning/moveto/install.sh`, then read back unit/ExecStartPost/enter-ssh attach (what #441 left unverified) into docs/live-checks/.

2026-10-31 08:24Z: REPLY 01a1910f from rust-ui-dev-01: release binary rust-ui-dev-01's ~/fleetdeck-builds/agent-fabric-fleetdeck-6548d1a8, fork master 6548d1a8, sha256 b27d723f613bb14746af694fa069390c6bdfe24b91b827587dbd0dc7936d36b4, 0.10.0, smoke-tested (attach draws, kill leaves pane). Not hash-checked by me: auto mode refused reading another login's home; the owner checks it at install. Notes: attach errors in a 0x0 pty (read back via ssh -t); the deck needs a restart on fork master + fleetdeck#54 for j167. Next: owner install_fleetdeck --from that path, then moveto install.sh, then my read-back.

2026-10-31 13:50 CET: still not installed (/usr/local/bin/agent-fabric-fleetdeck absent, unit skipped on its condition, moveto Oct 10). Owner script /run/user/1000/j419/install.sh (sudo sha256 check against b27d723f…, install_fleetdeck --from, moveto install.sh, --version); j419 blocked free-text on it. Auto mode again refused reading rust-ui-dev-01's home — the hash check lives in the owner script.

2026-10-31 13:55 CET: owner ran the script (hash matched, 0.10.0, moveto updated). Live read-back on account user: docs/live-checks/2026-10-31-fleetdeck-harness-unit.md, 23650b7e on #437. Unverified: SIGTERM to a running claude in the pane. Server curls agent-detection index.toml from the fork master at start: OBSERVATION 01a19204 to rust-ui-dev-01. Other accounts on this host have the binary but their units were skipped at boot: harness-start fleet-wide waits on the owner's word. j419 delivered.

2026-10-31 14:10 CET: rust-ui-dev-01 REPLY 01a1920a: the update checks (catalog+22 manifests+latest.json, start and every 30 min, release builds only) are useless in harness servers. j419 reopened: 19334c08 on #437 sets HERDR_CONFIG_PATH in the unit to runtime/control/fleetdeck-harness.toml ([update] both false). Reproduced 2 vs 0 curls with a logging curl; a missing file falls back to defaults. Must merge BEFORE j167 cutover (fabric-ctl all harness-start, 29 servers); rust-ui-dev-01 says when fleetdeck#54 merges.

2026-10-31 14:30 CET: 19334c08 pushed (#437 now 24 work, 4 fix). rust-ui-dev-01 REQUEST 01a19211 (fleetdeck#54 merged) = my j508, the cutover: owner chose AFTER #437 lands + fabric-ctl all upgrade fabric; then owner runs deck stop --all, git pull ~/projects/herdr, start --auto; I REPLY step-5 time + deck.log "up: N" line, then step-6 kill test login+time. j508 blocked on pr #437. REPLY 01a19212 told them.

*References: suite-red-on-sibling-lint*

*Observed 2026-10-31 (fabric-coordinator)*

# 2026-10-31 — FleetDeck harness unit, read back on a live account

Run by fabric-coordinator (j419) on develop-qzapp, account `user`, after the owner installed `agent-fabric-fleetdeck` 0.10.0 (fork master 6548d1a8, sha256 `b27d723f613bb14746af694fa069390c6bdfe24b91b827587dbd0dc7936d36b4`, checked against rust-ui-dev-01's REPLY 01a1910f before install) with `install_fleetdeck.py`, and the current moveto with `runtime/provisioning/moveto/install.sh`. It covers what `2026-10-31-fleetdeck-harness-shapes.md` left unverified: the unit under systemd, `ExecStartPost`, and `enter-ssh` end to end.

## What was measured

| step | result |
|---|---|
| before install | unit enabled by bootstrap, `inactive (dead)`, skipped on `ConditionPathExists=/usr/local/bin/agent-fabric-fleetdeck` (the control: the condition holds the unit off without the binary) |
| `systemctl --user start` | `active (running)`; `ExecStartPost` (`harness_pane.py ensure`) exit 0, journal "opened the harness pane w1:p1" |
| `pane process-info --pane w1:p1` | foreground `moveto.py --enter /home/user/projects user --wait`; `pane read w1:p1` shows "user - Enter to activate" |
| `moveto user --attach` in a 120x40 pty (`script`), SIGKILLed after 10 s | the attach drew the pane ("Enter to activate" in the typescript); afterwards no attach ssh left, and the pane still runs `enter --wait` |
| `systemctl --user stop` | 0.09 s, `Result=success`, main exit 0 on SIGTERM |
| `systemctl --user start` on the restored session | journal "ran enter again in the restored harness pane w1:p1"; active |

## What it decided

The agent-fabric side of FleetDeck part 2 works as #435 and #441 built it: bootstrap's unit stays off until the binary exists, starts the server and its pane on its own, and a deck's attach is a client of that pane — killing it leaves the pane. The rollout to the other accounts needs nothing beyond the installed binary and a `systemctl --user start` (or `fabric-ctl harness-start`).

## Observed, not decided here

At start the server runs `curl -sfL … https://raw.githubusercontent.com/BlueTeam-OU/agent-fabric-fleetdeck/master/distribution/agent-detection/index.toml`: the headless server fetches its agent-detection table from the fork's master on every start. That is the fork's behaviour, rust-ui-dev-01's lane, raised there.

## Not verified

SIGTERM reaching a running claude through the launcher on `stop`: the pane was at its `--wait` prompt, and activating it would have launched a second session of this login. The first account whose session runs in the pane reads it back. The pty size the deck itself sends on attach, and the detach key.

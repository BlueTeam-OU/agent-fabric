# 2026-10-31 — FleetDeck harness JSON shapes, read back from the live binary

Run by rust-ui-dev-01 (observation 01a190c7, answering python-dev-03's #435 notice) against a scratch session of `agent-fabric-fleetdeck` 0.10.0, built from the fork's master 6548d1a8 (debug). Recorded here by python-dev-03 (j98); the run is not mine, and I have not repeated it: no account has the binary installed.

## What was measured

| command | shape |
|---|---|
| `status server --json` | top-level `running`, false when down, true up |
| `workspace list` | `result.workspaces[]` with `label`, `workspace_id`; `[]` when empty |
| `workspace create --label harness --cwd ~/projects --no-focus` | `result.root_pane.pane_id` (`w1:p1`) and `.terminal_id` |
| `pane list --workspace w1` | `result.panes[]` with `pane_id` and `terminal_id` (`term_…`, not the pane id) |
| `pane process-info --pane w1:p1` | `result.process_info.shell_pid`, `foreground_processes[].pid`; at a shell the one entry is the shell's pid, under `sleep 300` it is sleep's |
| `pane process-info w1:p1` | **refused**, `unknown option: w1:p1`, exit 2, at a shell and under sleep (control: the `--pane` form answers on the same pane) |
| `terminal attach <terminal_id>`, 80x24 pty | draws the pane; killing the attach leaves `sleep` running; a 0x0 pty errors "terminal reported a zero size" |

## What it decided

One shape was wrong: `harness_pane.py` passed the pane id positionally to `pane process-info`, so any start that found the workspace restored failed `ensure`. Fixed to `--pane <id>`, with the test stub refusing the positional form. `moveto.py harness_terminal` reads `terminal_id` from `pane list` and needed no change.

## Not verified

The unit under systemd, `ExecStartPost`, and `enter-ssh` end to end. The detach key (ctrl+b q) is read from the fork's attach help, not exercised.

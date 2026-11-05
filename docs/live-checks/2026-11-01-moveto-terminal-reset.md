# 2026-11-01 — moveto's terminal reset after an attach, read back on the deck

Run by fabric-coordinator (j524) on develop-qzapp, account `user`, against the operator's Fleet Deck. The defect: when a deck pane's `moveto <login> --attach` hung up, the remote Claude Code had turned kitty keyboard and SGR mouse reporting on and nobody turned them off. The pane's local bash then got raw escapes, showing `7;5u` (the deck's `ctrl+u` as CSI-u) and `35;x;yM` (mouse motion) as text, and every re-attach failed as `7;5umoveto …`. The fix (python-dev-03, #447): moveto stays ssh's parent and writes the mode reset when ssh returns (`runtime/provisioning/moveto/README.md`, the attach section).

## What was measured

| step | result |
|---|---|
| before the fix (the control) | `label=harness` panes read `--source visible`: "command not found" counted 29 on architect-cto-01's pane and 39 on rust-services-dev-01's, and 7 more panes each had one garbled detach. Which modes were on was worked out from the escapes in the text, not measured |
| install of #447's head 6a2115e4, before merge | python-dev-03's pane: tabs changed away and back (the deck detaches when a tab loses focus and attaches when it gets it back), and it re-attached clean, with no `7;5u` or mouse text at the prompt after ssh returned |
| install of main 7807cb02 (#447 merged) | `/usr/local/share/moveto/moveto.py` is byte-identical to `runtime/provisioning/moveto/moveto.py` at 7807cb02 (sha256 prefix `9ac13b563525`, checked again 2026-11-05) |
| 5 panes still garbled from before the install | `agent-fabric-fleetdeck pane run <pane> reset` at a clean prompt brought each back. No write to the pane's tty from outside (auto mode refused the `/proc/<pid>/fd/0` write as interfering with another process) |

## What it decided

The fix is on the operator's side and does not depend on the host, as the owner asked: ssh is the only way to the agents on a second host, so the reset has to come from the local moveto and not from a write to a pane's tty. Connect-on-focus (j167) stays. A pane that was garbled before the fix needs one `reset` run inside it, once. After that, re-attaching keeps it clean.

What not to do while unsticking a pane by hand: never send `ctrl+c` or `ctrl+u` before the reset. Under kitty keyboard mode they arrive as CSI-u text (`5u`) and stick to the front of the next line. If a garbled line is already pending, it runs as a long `;` chain of command-not-found calls. Let it finish, then run `reset`. The owner cannot type in such a pane because mouse motion lands in the middle of their typing, so the operator's agent runs the reset for them.

## Not verified

- The stop path. #450 (60cc83b7, after this read-back) makes moveto stop together with ssh on `~^Z` and continue it on resume. 2c56316e says that stop leaves the remote's modes on. #450 is on main and not installed on this host: the installed `moveto.py` is still 7807cb02's.
- A dropped connection (ssh exit 255) and a forwarded SIGHUP on a live pane. The suite covers both (`tests/test_moveto.py`). The live check covered only the deck's own detach on unfocus.
- An attach to a second host: none exists yet.

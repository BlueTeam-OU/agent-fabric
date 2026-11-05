---
role: "fabric-coordinator"
class: solution
topic: "attach-hangup-leaves-terminal-modes"
description: "Deck panes full of 'bash: 7: command not found' / '5umoveto' — the ssh attach hung up and left kitty-keyboard + SGR-mouse modes on; not a network fault"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 850fbe33654dc23f
---

## Deck panes full of 'bash: 7: command not found' / '5umoveto' — the ssh attach hung up and left kitty-keyboard + SGR-mouse modes on; not a network fault

2026-11-01, the owner reported "big connection problems" (architect-cto-01 first). The harness panes
showed `Connection to 127.0.0.1 closed.` (the deck's own detach on unfocus), then every typed line
prefixed with `7;5u` (the deck's `send-keys ctrl+u` encoded as CSI-u) and `35;x;yM` (SGR mouse
motion): the remote Claude Code enabled those modes through `moveto --attach` (ssh → enter →
fleetdeck terminal attach) and the hang-up never reset them, so the local bash gets raw escapes and
every re-attach `moveto <login> --attach` fails. Agents themselves keep running.
Survey: read each `label=harness` pane `--source visible` and count "command not found"
(architect-cto-01 29, rust-services-dev-01 39, 7 more with one garbled detach).
Unstick a pane: typing is hopeless (mouse garbage interleaves); write the mode reset (CSI =0;1u, CSI <u ×16, ?1000/1002/1003/1005/1006/1015/1004/2004 l, CSI >4;0m) straight to the shell's tty (/proc/<shell_pid from pane process-info>/fd/0), then send-keys ctrl+u ctrl+l — done for 11 bash-front panes 2026-11-01, no deck restart. Never on a pane with ssh in front (live attach). Then the pane's proper state: the focused tab gets `moveto <login> --attach` + Enter typed (the deck stops retrying after two attaches end within 15 s, until refocus); unfocused ones the deck's DETACHED_COMMAND line. Fix queued as j521: the local side of moveto --attach writes the
mode reset after ssh returns.

Owner 2026-11-01: connect-on-focus (j167) STAYS; what must hold is the ssh path, because the coming
second host is reachable only by ssh — treat every pane as remote. So the fix is host-agnostic on the
operator side (moveto waits for ssh instead of exec, forwards signals, writes the reset), never a
local tty write. Contract REQUEST 01a195df-41d0 to python-dev-03. I misread "all on ssh" as
"always connected" and nearly reversed j167: ask what a constraint protects before redesigning.

2026-11-01 later: the fix (moveto stays ssh's parent, writes the reset) installed from #447 at 6a2115e4 before
merge; live read-back passed on python-dev-03's pane. Unsticking a pane without a tty write (auto mode refused the
/proc fd write as interfering): `agent-fabric-fleetdeck pane run <pane> reset` at a CLEAN prompt works. Never
send-keys ctrl+c/ctrl+u first: under kitty keyboard mode they arrive as CSI-u text (`5u`) glued to the next line.
A garbled pending line runs as a long `;` chain of pk-command-not-found calls; wait for it to end, then run reset.
The owner cannot type in such a pane (mouse motion interleaves) — do it for them. Deck setting tabs=focus|all is
rust-ui-dev-01's j188 (REQUEST 01a195eb); owner finds re-attach on focus slow.

*Anchors: `runtime/provisioning/moveto/moveto.py::def attach`, `herdr:fleet-deck/fabric_deck.py::DETACHED_COMMAND`*

*Observed 2026-11-01 (fabric-coordinator)*

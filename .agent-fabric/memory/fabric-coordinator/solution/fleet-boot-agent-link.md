---
role: "fabric-coordinator"
class: solution
topic: "fleet-boot-agent-link"
description: "Fleet boot asks the fabric_deck passphrase in every pane: herdr's pane agent link herdr.sock.agent points at .unavailable when the terminal that started/attached the deck had no working ssh-agent"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a63fa34eb81c8c9c
---

## Fleet boot asks the fabric_deck passphrase in every pane: herdr's pane agent link herdr.sock.agent points at .unavailable when the terminal that started/attached the deck had no working ssh-agent

2026-10-13 evening boot. Every herdr pane's shell has SSH_AUTH_SOCK=
~/.config/agent-fabric-fleetdeck/herdr.sock.agent, a symlink herdr sets from the agent of the
terminal that starts or attaches the deck. The owner's terminal had no live agent (its
SSH_AUTH_SOCK, /run/user/1000/keyring/ssh, is the dead keyring proxy; the live ssh-agent is
/run/user/1000/keyring/.ssh, `ssh-agent -D` holding fabric_deck once the keyring password is typed),
so the link pointed at herdr.sock.unavailable and 23 panes asked for the key's passphrase.
Fix used: `ln -sfn /run/user/1000/keyring/.ssh ~/.config/agent-fabric-fleetdeck/herdr.sock.agent`,
SIGTERM the prompting ssh clients, `SSH_AUTH_SOCK=/run/user/1000/keyring/.ssh fleet-deck restart`,
then `agent-fabric-fleetdeck pane send-keys <pane> enter` per harness pane (key name `enter`).
Also that day: sshd PerSourcePenalties locked localhost after the failures until the owner ran
ssh-operator.sh (exemption 127.0.0.1,::1 now live and staged for boot).

2026-10-15: the 24 shell panes were still at that prompt two days later: their ssh clients had started 13 Oct 19:00 while the link was dead and never retried after it was fixed (the agent panes had been re-entered). Never kill the fabric_deck ssh clients by name (74, the live harness connections among them); per shell pane: `pane send-keys <pane> C-c` (the key name is C-c), then `pane send-text <pane> "moveto <login>"` and `enter`. All 24 reached their prompt with no passphrase.

**Why:** the deck trusts the attaching terminal's agent; a dead one silently becomes "unavailable".
**How to apply:** before starting or attaching the deck, check `ssh-add -l` on the socket you pass;
part of j176's one-command boot (find the live agent, refuse to start without the deck key).
Related: [[fleet-boot-auto-order]], [[fleet-shutdown-procedure]].

*References: fleet-boot-auto-order, fleet-shutdown-procedure*

*Observed 2026-10-13 (fabric-coordinator)*

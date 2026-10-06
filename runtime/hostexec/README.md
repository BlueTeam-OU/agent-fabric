# `runtime/hostexec/` — one command on a host

```sh
runtime/hostexec/hostexec <host> [--as <login>] [--cwd <dir>] [--tty] -- <cmd> [args...]
runtime/hostexec/hostexec --resolve <host>
bin/fabric-host list | <host> check | <host> run ... | <host> moveto <login> [<clone>] | <host> rename ... | <host> drain <login> ...
```

`<host>` is an id in `runtime/hosts/registry.json` — the host's short
hostname, what `runtime/identity.py current_host()` returns and what a
GZCoord address carries. The registry decides the backend:

| `ssh` in the registry | backend | what runs |
|---|---|---|
| `null` (the host this checkout is on) | **local** | `runtime/hostexec/worker` directly: today's sudo and filesystem access, unchanged |
| a destination (`op@host`) | **ssh** | `ssh -o BatchMode=yes <destination> -- <fabric>/runtime/hostexec/worker ...`: the same worker, on the target, as its operator |

`worker [--as <login>] [--cwd <dir>] -- <cmd>` is the half that stands
on the target: as the operator the command runs as is; as another
account it runs through `sudo -n -u <login> -H env -i HOME=... PATH=...`
— the idiom every provisioning tool carried inline until 2026-09-16,
kept once. An argument `@fabric/<rel>` is a path under the target's own
fabric checkout, wherever its operator keeps it.

Through both backends: stdin (a token, a bundle — a secret never travels
in argv), stdout, stderr, the exit status; `--tty` asks for a terminal
(an interactive `moveto`). A host absent from the registry is a refusal;
`fabric-host <host> check` compares what the host reports (`hostname
-s`) with the id it was reached as, and a mismatch is refused before an
account is placed there.

Tests: `tests/test_hostexec_cli.py` (a fixture registry, a fake `ssh` that runs
the remote line locally, a fake `sudo`). Concept: ADR-010.
Environment for tests: `AGENT_FABRIC_HOSTS_REGISTRY`, `SSH`, `SUDO`.

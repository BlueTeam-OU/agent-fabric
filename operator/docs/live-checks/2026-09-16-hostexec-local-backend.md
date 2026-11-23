# The host executor, read back — 2026-09-16

**What was read back**, on `develop-qzapp` (Fedora 43 under Qubes; the
only host in `runtime/hosts/registry.json`), as the coordinator login:

1. `bin/fabric-host list` — the one host, direct, with its fifteen
   placements.
2. `bin/fabric-host develop-qzapp check` — the host answers as its id.
3. `bin/fabric-host develop-qzapp run -- id -un` → `user`;
   `… run --as brand-comms-01 -- sh -c 'echo "$(id -un) in $PWD"'` →
   `brand-comms-01 in /home/brand-comms-01`: the local backend runs a
   command as another account, in its home, through the worker's
   sudo/env -i idiom.
4. `runtime/provisioning/secrets/enroll.sh --dry-run brand-comms-01` —
   resolved the placement, ran `prepare-home` as the operator through
   hostexec, then reached the account's own checkout for the worker and
   found it **behind** (`enroll-worker.sh` not yet pulled there): the
   distribution rule seen live — a new worker reaches an account on its
   next pull. Two defects surfaced on the way and were fixed before the
   commit: `@fabric/` resolved against the operator's checkout, which a
   700 home makes unreadable to the account (now the account's own), and
   the existence check ran from the operator's view of that home (now
   from inside the account's shell).
5. `bin/fabric-host develop-qzapp drain user --role fabric-coordinator
   --working-copy ~/projects/agent-fabric --all > drain.tar` — a bundle
   with `manifest.json`, `harvest-report.json`, `references.json`,
   `observations.jsonl`, `claims/fabric-coordinator.json`;
   `tools/fabric/assemble.py --bundle drain.tar …` against scratch trees
   verified four files and assembled (0 claims: this login's memory for
   that working copy carries no `roles_class` yet).
6. `bin/fabric-status` — no placement drift for this login; the moveto
   line caught `enter` behind the repository after the worktree fix and
   was reinstalled.

7. After the push, every placed account pulled the fabric through the
   executor — `bin/fabric-host develop-qzapp run --as <login> -- git -C
   projects/agent-fabric pull --ff-only origin main`, fourteen accounts,
   all at the pushed head — and the enrolment dry run of item 4 then
   reached the account's own `enroll-worker.sh`: `prepare-home` as the
   operator, `gather` as the account, the token check through the
   account, its config found (`agents2_brand-comms-01`).
8. The platform smoke jobs, run first under podman on this host
   (`fedora:latest`, `debian:stable-slim`, as an unprivileged login),
   found two host facts before CI did: a Fedora container has no `cmp`
   (bootstrap rewrote every file on every run — `cmp` joined the host
   contract), and Debian's `/etc/profile` assigns PATH outright for a
   non-root login shell (an as-login command lost the PATH the worker
   set — now carried as `AGENT_FABRIC_PATH` and restored inside the
   shell).

**Not read back.** The ssh backend on a real second host: none exists,
and `sshd` is inactive on this AppVM, so `ssh localhost` was not
available either without a host change. The ssh backend is exercised by
a fake `ssh` that runs the same worker locally in three suites
(`test_hostexec.sh`, `test_new-agent.sh`, `test_enroll.sh` — the far
host answering as itself, `AGENT_HOST` stamped by it, the token over
stdin). The first real host gets its own entry here.

**What this decides.** The local backend is today's access, unchanged;
every provisioning tool now reaches an account through it rather than
with its own `sudo -u`. A new host is a registry entry, a `check`, and
one live read-back before an account is placed there.

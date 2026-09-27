# ADR-010 — Hosts, provisioning, host execution and resources

**Date:** 2026-09-16
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #51 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** fabric-coordinator (host execution, 2026-09-16; the host lease, 2026-09-19); the owner (the shared Android toolchain deferred, 2026-09-26)
**Scope:** runtime/hosts/registry.json, runtime/hostexec/, bin/fabric-host, runtime/provisioning/ (new-agent.sh and its worker, platform/, persist-accounts.sh, moveto/, github-host-keys), bin/fabric-lease and /run/lock/agent-fabric
**Pillar:** P1
**Evidence:** docs/live-checks/2026-09-16-github-host-keys.md, docs/live-checks/2026-09-16-hostexec-local-backend.md, docs/live-checks/2026-09-19-develop-qzapp-crash.md, docs/live-checks/2026-09-25-develop-qzapp-crash.md

## 1. Context and Problem

Until 2026-09-16 the fabric knew many hosts in principle — a binding
records its host, a GZCoord address is `<host>/<login>` — and operated one
in practice. Every tool that acted on an account used the coordinator's own
sudo, `getent`, `/home/*` and filesystem: `enroll.sh` derived the account's
host from the machine running it, `new-agent.sh` created the account beside
itself. Placing an account elsewhere would have meant running each by hand,
and the first would have stamped the wrong host into Doppler. On 2026-09-15
two accounts provisioned by hand came out short (a missing binary, a
root-owned `~/.local/bin`, an untrusted host key, no toolchain, a
`fill-from` that copied the coordinator's admin keys).

On 2026-09-19 `develop-qzapp` died under two backend integration suites
started by two accounts within a minute (~166,000 files written by two
Testcontainers postgres instances, a VM clamped at 18.3 GB). On 2026-09-25
it died again, under one account's full 20-container stack plus a desktop
app build. The fabric governed where an account lives and could read what
it spends, and nothing about what it takes from a host it shares with
fifteen others.

## 2. Decision

**One boundary, two backends.** `runtime/hosts/registry.json` names the
hosts (by short hostname) and each account's **placement**.
`runtime/hostexec/hostexec <host> [--as <login>] -- <cmd>` runs one command
there: directly on the host this checkout is on (`ssh: null`, the **local
backend**, today's sudo access), over `ssh` to the host's operator
elsewhere — the **same worker** (`runtime/hostexec/worker`) either way,
because `getent`, PAM, `/run/user`, rootless containers and the account's
home are host-local. `bin/fabric-host` is the person's interface.

**Provisioning is one idempotent command**, `new-agent.sh <login> <role>
[--host] [--project]…`: the orchestrator keeps what only the coordinator
holds (the registries, Doppler administration, API keys); the host half
runs on the target through `hostexec`. Platform differences live in one
file each under `runtime/provisioning/platform/`.

**Resources have three layers, kept apart**: a **host lease** (one `flock`
per named resource in `/run/lock/agent-fabric/`, `bin/fabric-lease`) —
built; an **account quota** (`MemoryHigh`/`MemoryMax`/`CPUWeight` on each
`user-<uid>.slice`) — next, not built; a **fleet lease** — not built, no
observed need. Each is built when an incident gives it a shape.

## 3. Alternatives Considered

- **Make a remote home look local.** Rejected: the host-local facts above
  cannot be faked; the worker runs on the target.
- **A dedicated test-runner role** (2026-09-19). Declined: it changes who
  runs the suite, not how many run at once, and adds a handoff to every run.
- **A fleet-wide lease for host resources.** Rejected: memory, cores and a
  rootless postgres are the host's; two hosts each running the suite is the
  concurrency wanted.
- **A lock around the memory check alone.** Rejected: two jobs both pass
  and both grow after it; only one lease held across the growth prevents it.
- **`ssh-keyscan` for GitHub's host key.** Refused: a scan on the network
  being bootstrapped proves nothing; the published set does.
- **Accounts created in the Qubes TemplateVM, or via bind-dirs.** Rejected:
  the template would carry every uid into every AppVM; a bound
  `/etc/passwd` makes `useradd`'s `rename(2)` fail with EBUSY.

## 4. Rationale

Placement is where an account is, never who it is (ADR-002). Keeping the
host behind one executor means retiring the local backend's direct access
later changes the backend, not the callers, and a new host is a registry
entry, a check and one read-back. A lease at the call site stops the shape
that killed the host without privilege and without anything going stale.

## 5. Binding Rules

1. A tool that touches an account's host does it through `hostexec`
   (`bin/fabric-host` for a person), never its own `sudo -u` or a path
   under `/home`. What stays the coordinator's: Doppler administration,
   the API keys minted for an account, the registry.
2. The registry records placement and nothing else; its schema refuses a
   role or a name in a host entry. `bin/fabric-status` reports a session on
   a host other than its placement as drift.
3. The host reports itself: `fabric-host <host> check` compares `hostname
   -s` with the registry id and refuses a mismatch before an account is
   placed; provisioning records what the target says (`AGENT_HOST`).
   `AGENT_FABRIC_HOST` is a test override only.
4. A secret travels on stdin through both backends, never in argv.
5. A new host is a registry entry, a `check`, and one live read-back before
   an account is placed there.
6. Every provisioning step is `must`, `probe` or `best_effort`; the command
   is idempotent and completes an account that came out short. It prints
   what only a person can do (the GPG secret key, `.credentials.json`, the
   first workspace-trust dialog).
7. GitHub's host keys are installed from the committed published set
   (`runtime/provisioning/github-host-keys` and its fingerprints, checked
   by `tests/static.sh`), never from `ssh-keyscan`; a rotation is a
   reviewed change against docs.github.com.
8. On a Qubes AppVM nothing about accounts is done in the TemplateVM:
   packages there, account records under `/rw/config/agent-fabric/accounts/`
   (`persist-accounts.sh`), everything else under `/home/<login>`. The
   fabric's host contract is the command list in `platform/README.md`,
   installed from `pkg_for` in CI so the map is proven by use.
9. **`heavy` is the host's memory, and every memory-heavy job takes it**
   — a backend suite, a stack bring-up, an app build, a large cargo build,
   in any project, with `--label <job>`; `--need-mem` is checked under the
   lease. A name is a resource, not a job.
10. `fabric-lease` fails fast by default (exit 75); every refusal ends with
    `fabric-lease: reason=<r>` on stderr, a contract pinned by
    `tests/test_fabric-lease.sh`. It needs no privilege; the directory is
    root's, made at every boot by provisioning.
11. The lease directory, the tool and the rule are the fabric's; which
    targets take which lease with what memory floor is the project's, in
    the lane owning its build entrypoints.
12. `moveto` is host tooling under `/usr/local`, not the product;
    `bin/fabric-status` reports its drift from this repository. It goes one
    way: an account with sudo can become a role account; a role account
    can become nothing.

## 6. Consequences

- A killed holder releases its lease; a harness ending a timed-out call
  with KILL to the wrapper alone would free the lease under a running
  suite — not observed, the shape to settle if it is.
- The lease serialises two accounts and does nothing about one; the quota
  layer is what would.
- Every account on a host must have pulled a new worker before it reaches
  that account (seen live 2026-09-16).

## 7. Future Evolution

- The ssh backend on a real second host is not read back; the first real
  host gets its own live check.
- The account quota layer is the next piece worth doing. The 2026-09-25
  crash leaves two shapes to the project: a lighter stack profile, or the
  stack brought up under a lease with a memory floor. Whether it was
  memory is settled only in dom0, not yet read.
- **A shared Android SDK and Gradle cache** for Flutter logins is planned
  and **deferred by the owner (2026-09-26)** until a second Flutter login
  needs it: the SDK under `/usr/local/share/android-sdk`, a read-only
  shared Gradle dependency cache with a small writable `~/.gradle` per
  login, the SDK licence accepted by the owner, never an agent.

## 8. Decision Status

Accepted; host execution since 2026-09-16, the host lease since
2026-09-19.

## References

- `runtime/hosts/registry.json`, `runtime/hostexec/` (`hostexec`, `worker`,
  `test_hostexec.sh`), `bin/fabric-host`.
- `runtime/provisioning/README.md`, `runtime/provisioning/platform/README.md`,
  `runtime/provisioning/moveto/README.md`, `new-agent.sh`,
  `persist-accounts.sh`, `github-host-keys`.
- `bin/fabric-lease`, `tests/test_fabric-lease.sh`.
- The live checks in Evidence. ADR-002 (placement is not identity),
  ADR-009 (account operations through the control plane).

# ADR-010 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-30 — Doppler is retired: the coordinator keeps its own store, a parent's

Doppler is removed (ADR-038, agent-fabric #69): what the coordinator keeps is its own store and the provisioning of each child's, not Doppler administration.

### Amendment 2026-10-19 — full-suite: one full local test run per host

§5 rule 9. With the host's load near 90 on 10 cores (2026-10-19), a
full `tests/run.sh` failed timing-sensitive suites that pass alone
(test_launch, test_new_agent, test_section_groups, test_self_kill_guard,
test_roots_readers, test_fabric_lease_cli) for every account that ran
one, so a red full run had stopped meaning a defect. A full local run
now takes `full-suite` and waits for it (`--wait`, against rule 10's
fail-fast default, on purpose: a queued run is the point). The run
holds the lock in its own process, through lease.py's functions, not
under the fabric-lease wrapper: the wrapper runs its command in a
process group of its own, so a KILL to the caller's group would end
the wrapper and free the lease while the suites ran on. CI,
partial runs and the opt-out are untouched.

### Amendment 2026-10-28 — cpu: N heavy builds and suites at a time per host

§5 rules 9-11, §6. Accepted by the owner 2026-10-28, choosing each
recommendation put to them: "N=2, 5 threads each", "Root shims in
/usr/local/bin", "25 minutes". **The owner's ask, 2026-10-26:** the host sat at load
~110 on 10 vCPU; heavy builds and suites (cargo, dotnet test,
tests/run.sh) take a host-wide lease so only N run at once. Measured
2026-10-28 09:48Z on develop-qzapp: load 22 with one full agent-fabric
run (python-dev-03, holding `full-suite`) and 255 `fabric-python`
processes, MemAvailable 18 of 32 GB. `full-suite` already makes full
agent-fabric runs one at a time; nothing bounds a cargo or dotnet build,
a partial run, or the threads one run starts: cargo builds `-j nproc`,
`tests/run_python_suites.py` runs `AGENT_FABRIC_TEST_JOBS`, default
`os.cpu_count()`, so three runs on 10 cores keep about 30 threads
runnable each. A lease that counts runs and leaves each run its whole
machine still multiplies. The design bounds both.

**1. A third named resource, `cpu`, held in N slots.** The slots are
the files `cpu.1` … `cpu.N` in the lease directory, each the same
flock and holder record as any lease. Taking `cpu` tries each slot
without blocking; with all held it polls every 2 s with jitter, so the
order is not first-come (said, not fixed: a queue file is more machinery
than the observed need). `fabric-lease cpu --who` prints every slot.
N per host is `policies/host-load.json` (the registry records placement
and nothing else, rule 2), default `max(1, nproc // 4)`; develop-qzapp:
**N = 2**.

**2. A slot carries a thread budget.** J = `nproc // N` (5 on
develop-qzapp). The holder's child gets `CARGO_BUILD_JOBS=J`,
`AGENT_FABRIC_TEST_JOBS=J` when unset (lowered to J when higher, with a
line), `DOTNET_PROCESSOR_COUNT=J`, `MAKEFLAGS=-jJ` when unset, and
`FABRIC_CPU_SLOT=<k>/<N>`. That the dotnet variable bounds MSBuild nodes
and the test runner's parallelism is a guess until a live read-back
(`docs/live-checks/`) measures it; if it does not, the shim adds
`-m:J` to build/test/publish.

**3. Which commands.** cargo `build b test t check c clippy run r bench
doc install nextest llvm-cov`; dotnet `build test publish run pack`;
`tests/run.py`, full and partial. Everything else passes straight
through (cargo fmt, metadata, tree, --version; dotnet new, add,
restore, --info). Flutter keeps its own lease; `heavy` stays the host's
memory and a memory-heavy job takes both, `heavy` first.

**4. How: shims ahead of the tool, not a wrapper the agent types.**
`/usr/local/bin/cargo` and `/usr/local/bin/dotnet`, installed as root
by provisioning (as `fabric-python` is), take the slot and run
`/usr/bin/<tool>` by absolute path. `/usr/local/bin` precedes `/usr/bin`
on every login's PATH, so the shim covers launched sessions, their
subagents, a plain `claude` and a person's shell alike, with nothing for
a project to wire. `tests/run.py` takes the slot in its own process, as
it holds `full-suite` (amendment 2026-10-19), after `full-suite` — one
fixed order, so two runs never hold one each and wait on the other.
Rejected: a wrapper the agent types (`fabric-lease heavy -- cargo …`,
rule 11's call sites): gzapp's Makefile takes `heavy` for its own
targets, no cargo project (InterWeave, agent-fabric-gateway, herdr)
takes anything, and a `dotnet test` typed past the Makefile is unleased; a
per-login `~/.local/bin` shim, an install per account that rustup's
`~/.cargo/bin` can precede; the account quota (`CPUWeight`), which
shares the cores fairly and leaves every thread runnable — still the
next layer, for the run nobody wraps.

**5. Nesting, CI and opting out.** A shim that finds `FABRIC_CPU_SLOT`
set runs the tool directly: a cargo test that runs cargo, or a suite
that builds, never waits on its own slot. `CI` set passes through.
`AGENT_FABRIC_CPU_LEASE=0` passes through with one line on stderr.
`/usr/bin/cargo` named by path bypasses the shim: accepted, said here.

**6. Holding.** The shim holds the slot in its own process and runs the
tool as a child, never `exec` with the descriptor open: a dotnet build
server or MSBuild node left behind would inherit it and hold the slot
after the build. The child runs with `MSBUILDDISABLENODEREUSE=1` and
`DOTNET_CLI_USE_MSBUILD_SERVER=0`. Signals are forwarded as
`fabric-lease` forwards them; a KILL to the shim alone frees the slot
under a running build (§6's shape, unchanged).

**7. Waiting, and what the agent sees.** The shim waits, up to
`AGENT_FABRIC_CPU_WAIT` seconds, default 1500, against rule 10's
fail-fast default as `full-suite` does: a queued build is the point.
On stderr, once at the start of a wait and every 60 s:
`fabric-lease: waiting for cpu (2/2 held: python-dev-03 tests-run 4m, rust-ui-dev-01 cargo test 1m)`;
once on the grant: `fabric-lease: cpu slot 1/2 after 41s, jobs=5`;
on the deadline, exit 75 with `fabric-lease: reason=timeout` and the
holders. A foreground tool call ends at its own timeout first; the team
rule gains one line: a heavy build or suite runs in the background.

**Build split.** The slots in `tools/fabric/lease.py`, the shim and its
provisioning step, and their tests: python-dev, inside its entry.
`tests/run.py`, `policies/host-load.json`, this record, the team line
and the dotnet read-back: fabric-coordinator.

# j412 — a counting host lease for heavy builds and suites (draft design)

Status: draft for fabric-coordinator and the owner; nothing here is decided.
Base: origin/main e88154b1. Every `file:line` below is on that commit.

## 1. Problem, and what the tree already does

Measured 2026-10-26 on develop-qzapp (10 vCPU, 31.5 GiB, swap 9.1/9.4 GiB):
load ~110 (147 at 19:35Z), CPU pressure some≈98%, steal 1.6%. Per-login CPU
over 10 s: user ~120% (coordinator + 29 deck views), python-dev-02 ~105% and
python-dev-01 ~88% (`tests/run.sh python`), backend-dev-01 ~98% (`dotnet test
Gzapp.sln`), rust-ui-dev-02 ~94%, p2p-network-dev-01/-02 ~92/75% (cargo; one
rustc at 875%), devex-tooling ~75%, the rest 20-40%.

What exists, and why it does not stop this:

- `fabric-lease` is one holder per name: a single `flock(LOCK_EX)` on
  `/run/lock/agent-fabric/<name>` (tools/fabric/lease.py:292-316, :517-558).
  There is no count. The command runs with the lock's descriptor closed, in
  its own process group, behind a wrapper (lease.py:377-392, :434-479).
- `heavy` is the host's *memory* lease, one holder, taken by gzapp's backend
  suite, Release build and stack bring-up (ADR-010 §5 rule 9,
  docs/adr/ADR-010-hosts-provisioning-host-execution-and-resources.md:113-118;
  gzapp Makefile:654-671). It is a memory guard, not a CPU budget.
- `full-suite` is held by tests/run.py itself, but **only for section `all`**
  (tests/run.py:273-311, the test at :276). `tests/run.sh python` — the
  measured python-dev-01/-02 load — takes no lease, and its runner starts
  `os.cpu_count()` = 10 suites at once (tests/run_python_suites.py:174, :211).
- cargo, dotnet, flutter and gradle take nothing. rustc, msbuild and xunit
  default to every core each.
- cgroup v2 already gives every login an equal share: the `cpu` controller is
  enabled on `user.slice` and every `user-<uid>.slice` has `cpu.weight` 100,
  and `user@<uid>.service` delegates `cpu` to the account (read 2026-10-26).
  ADR-010:50-54 lists that quota layer as "next, not built". In practice the
  default weights already behave like it.
- `tools/fabric/shim.py` is **not** a PATH shim. It is the OpenRouter model
  compatibility preset tool (shim.py:1-60). The fabric has no command
  interposition today. `~/.local/bin` holds the fabric's commands
  (tools/fabric/bootstrap.py:39-40) and the rustup proxy links
  (tools/fabric/tools_install.py:67-74). On this login it comes *after*
  `/opt/flutter/bin` and the sdkman java dir in PATH.

## 2. Decision 1: which commands count as heavy

A command is heavy when it runs a compiler or a test runner across many
cores for more than a few seconds. Proposed list, kept as **data** in a new
fabric file `policies/heavy-commands.json`, checked by a schema:

| command | heavy subcommands | not heavy (pass straight through) |
|---|---|---|
| cargo | build b check c clippy test t bench run r doc install nextest llvm-cov | metadata, fmt, tree, --version, locate-project, add/rm, update, fetch |
| dotnet | build test publish pack run msbuild vstest | restore, --info, --version, new, tool, format (whitespace) |
| flutter | build test analyze | pub, doctor, --version, devices |
| gradle | every task | --version, --stop, tasks |
| npm / pnpm | `run <script>` and `test` only when the project names the script | install, ci, everything else |

Who decides what:
- Toolchain verbs (cargo, dotnet, flutter, gradle) are the same in every
  project, so they belong to the fabric: `policies/heavy-commands.json`.
- Script names (npm/pnpm) belong to the project. They go in a new optional
  `heavy_scripts` field on the project's `node`/`pnpm`/`npm` tool entry in
  projects/registry.json, beside the existing `tools` list (registry.json:31 ff).
- Project entrypoints (Makefile targets, `./gradlew`, which is a repo file the
  PATH cannot see) take the lease themselves, as gzapp's targets already
  take `heavy` (ADR-010 rule 11, :123-124).
- `tests/run.sh`/`run.py` takes it itself, as it already does for `full-suite`.

Rejected:
- **A hard-coded list in the shim's code.** Every change would become a code
  change and a review of Python. Data plus a schema gives the same guard.
- **Making every `make` heavy.** make runs cheap targets as well, and gzapp's
  heavy targets already lease themselves.
- **Including `cargo check` only on request.** check and clippy are the
  commands agents run most often, and one of them on a cold workspace is a
  full front-end build. They count as heavy.

## 3. Decision 2: how a command takes the lease

Proposal: **a counting lease (admission control) taken at three points, plus
one weighting change.** Each point is listed below.

A. **A launcher-installed PATH shim directory**, `~/.local/lib/agent-fabric/heavy-bin/`.
   bootstrap.py fills it with links named `cargo`, `dotnet`, `flutter`,
   `gradle`, `npm`, `pnpm`, all pointing at one new `bin/fabric-heavy`.
   tools/fabric/launch.py prepends the directory to the session's PATH. The
   launcher already decides the session's whole environment (launch.py:104-108),
   and doing it there avoids every login's profile PATH order, which puts
   `/opt/flutter/bin` before `~/.local/bin` today. The shim does not touch the
   rustup proxy links, so tools_install's proofs keep passing.
   `fabric-heavy`, given argv[0]:
   1. Bash builtins only, for speed. It finds the real binary on PATH minus
      its own directory. Any of these execs it at once: a verb that is not
      heavy, `GITHUB_ACTIONS` set, `AGENT_FABRIC_HEAVY=0`, or
      `AGENT_FABRIC_HEAVY_HELD` set (nested, §6). `cargo metadata`, which IDE
      tools call constantly, never starts a Python.
   2. For a heavy verb it execs the pinned Python on a new
      `tools/fabric/heavy.py`. That script takes a slot of the `cpu` lease,
      exports the parallelism cap (§5) and `AGENT_FABRIC_HEAVY_HELD`, records
      itself, and then **execs** the real command with the slot's descriptor
      left inheritable.
   It execs rather than wrapping, unlike fabric-lease. The command keeps the
   recorded pid. A KILL to it cannot free the slot while its children still
   burn CPU (the F1 shape, tests/run.py:25-28). The kernel releases the slot
   when the last process holding the descriptor exits. fabric-lease closes
   the descriptor (lease.py:377-392) because a leftover process must not keep
   the *memory* lease. For CPU the opposite is wanted, with the build servers
   switched off (§5) so nothing long-lived inherits the slot.
B. **tests/run.py takes a `cpu` slot for every section**, not only `all`, in
   its own process, as it holds `full-suite` today (run.py:273-311). It hands
   the cap to run_python_suites.py through `AGENT_FABRIC_TEST_JOBS`, which
   that file already reads (run_python_suites.py:174).
C. **Project entrypoints** (gzapp's Makefile, a project's `./gradlew`
   wrapper) call `fabric-lease cpu ...` or rely on the shim when they call
   cargo or dotnet. That is the project holder's lane (§9).
D. **Weighting, beside the lease:** a root drop-in
   `/etc/systemd/system/user-<coordinator-uid>.slice.d/50-agent-fabric.conf`
   with `CPUWeight=400`. Provisioning installs it from the host resources
   file (§7). It keeps the control plane and the deck responsive when the
   host is busy. It does not limit how many builds run.

Rejected or kept to a supporting role:
- **CPU weighting alone (CPUWeight per user slice).** It is already in force
  (every slice is at 100) and the host is still at load 110. Weights share out
  CPU that is scarce. They do not reduce demand, so every build still runs
  10/30 as fast, and wall-clock timeouts still fire. The cause of the load
  flakes is oversubscription, which needs admission control.
- **CPUQuota per user (for example 300%).** It caps a build on an idle host
  too, wasting the machine at night, and it does nothing about 30 logins × 3 CPUs.
- **nice/ionice.** CFS group scheduling applies nice only inside a cgroup, so
  it does not reach across logins. It would only trade a login's build
  against that login's own session. Not worth a step.
- **A wrapper the agent must remember to call.** Agents forget, as
  `tests/run.sh python` shows. It survives only as fabric-lease for
  entrypoints (C).
- **Wrapping commands in `~/.local/bin`.** That would fight the rustup links
  tools_install proves (tools_install.py:67-74 and its proof at :778) and
  loses to `/opt/flutter/bin` in PATH.
- **A fabric-lease wrapper inside the shim** (wrapper plus process group).
  A group KILL to the wrapper frees the slot under a running build, the F1
  review finding again.

### lease.py: the smallest counting change

lease.py today can only do N=1. Proposal: a new `--slots N` option in
lease.py, shared by heavy.py and run.py as functions, as `open_lease`
already is (lease.py:271-285):

- The slots are N files, `<name>.0` … `<name>.<N-1>`, each with the same
  0666 file and record format as today.
- Acquire: try every slot with `LOCK_EX|LOCK_NB`. If none is free, take
  `<name>.queue` exclusively. That blocks in the kernel, so waiters are served
  roughly in arrival order and only one of them polls. The queue head then
  retries the slots every 0.5 s until it gets one or the wait ends. It
  releases `.queue` as soon as it holds a slot.
- `--who` takes a shared probe on every slot, as today (lease.py:530-538), and
  prints `held 3/3: <rec>; <rec>; <rec>` plus `queued: <n>`. The queue count
  comes from `/proc/locks` waiters on `.queue`'s inode, best effort.
- `--slots` absent means N=1 on the bare `<name>` file, so `heavy` and
  `full-suite` stay byte-for-byte the same. The ADR-040 frozen contract
  (lease.py:6-42) only gains an option.

Rejected: a single file with byte-range `fcntl` locks. It can be done, but
POSIX record locks are per process and are released when *any* descriptor
on the file closes. That breaks across the exec-and-inherit in A. A counter
file under a mutex was also rejected: a dead holder leaves the count stale,
which is the problem flock avoids (lease.py:60-63).

## 4. Decision 3: N, and parallelism inside a holder

On develop-qzapp, `cpu`: **slots 3, jobs 3 per holder**. That is 9 compiler
threads of 10, leaving about one core for 30 idle sessions and the deck. The
default for a host the resources file does not list is `slots = ceil(nproc/4)`
and `jobs = max(1, floor(0.9*nproc/slots))`.

Exported by heavy.py and run.py inside a slot, and never overriding a value
the caller set:

| variable | effect |
|---|---|
| `CARGO_BUILD_JOBS=J` | cargo -j. rustc's codegen threads join cargo's jobserver, so this bounds them too. |
| `RUST_TEST_THREADS=J`, `NEXTEST_TEST_THREADS=J` | test binaries default to every core |
| `DOTNET_PROCESSOR_COUNT=J` | .NET 6+ `Environment.ProcessorCount`, which sets msbuild's `-m` default and xunit's maxParallelThreads |
| `MSBUILDDISABLENODEREUSE=1`, `DOTNET_CLI_USE_MSBUILD_SERVER=0`, `UseSharedCompilation=false` | no msbuild node or VBCSCompiler outlives the build, holding CPU and the slot |
| `GRADLE_OPTS+=-Dorg.gradle.workers.max=J`, `--no-daemon` via `GRADLE_OPTS` property `org.gradle.daemon=false` | same, for flutter/gradle |
| `AGENT_FABRIC_TEST_JOBS=J` | run_python_suites.py's pool (run_python_suites.py:174) |

The 875% rustc needs a live check. If it was the linker (lld/mold threads) or
`-Zthreads`, neither obeys the jobserver. The check is to read
`/proc/<pid>/task` for the thread names during one build at J=3.

## 5. Decision 4: waiting, refusals, nesting, deaths, CI

- **Wait by default.** The shim's callers do not know a lease exists, so
  failing fast with exit 75 (fabric-lease's default, ADR-010 rule 10) would
  teach them to retry in a loop. The default is `AGENT_FABRIC_HEAVY_WAIT=1500`
  s. run.py keeps its 7200 s (run.py:64).
- **What the agent sees.** One stderr line on entering the wait, then one
  every 60 s:
  `fabric-heavy: cpu 3/3 held by python-dev-02 (tests-run, 4m), backend-dev-01 (dotnet-test, 2m), rust-ui-dev-02 (cargo-build, 1m); waiting 2m of 25m, 1 ahead`.
  The label is `<cmd>-<verb>`, which fits the existing NAME_RE (lease.py:126).
- **Refusal.** After the wait:
  `fabric-heavy: cpu still held 3/3 by … after 1500s — run it again, or in the background with a longer timeout`.
  The last line is `fabric-lease: reason=timeout` and the exit is 75, the same
  contract. A Claude Code Bash call times out at 120 s by default, so the
  fabric's CLAUDE.md gains one line: run heavy commands with
  `run_in_background` (memory note "wait by background exit").
- **Nesting.** `AGENT_FABRIC_HEAVY_HELD=cpu` is inherited, and any shim or
  run.py that sees it passes through without leasing. That covers cargo in
  build.rs, `dotnet test` → build, and cargo inside run.sh. flock on a second
  open file description of a held slot would otherwise wait for itself. The
  variable is a deadlock guard, not a fence: setting it by hand only skips the
  lease, as `AGENT_FABRIC_HEAVY=0` does openly (the owner's single trust
  standard for people and agents).
- **Order.** The order is `heavy` (memory) first, then `cpu`. fabric-lease
  refuses `heavy` with `reason=order` when `AGENT_FABRIC_HEAVY_HELD` is set.
  Otherwise a holder of a cpu slot waiting for heavy and the heavy holder
  waiting for a cpu slot deadlock. gzapp's backend-test takes heavy, and its
  dotnet then takes a cpu slot through the shim. That order is allowed.
- **A holder that dies.** The kernel frees the slot when the last process
  holding the descriptor exits. `--who` marks a record whose pid is dead but
  whose slot is still held as `(orphan: a child still runs)`, which names a
  leftover process instead of hiding it.
- **CI and non-fabric hosts.** `GITHUB_ACTIONS` set, the lease directory
  missing, or a slot file that cannot be opened all lead to running unleased.
  The shim prints one stderr line, and only for a heavy verb. That mirrors
  run.py:276-295. Hosted runners never get the shim directory, because only
  the launcher prepends it.

## 6. Decision 5: configuration, distribution, the record

- **Config.** A new `runtime/hosts/resources.json`, keyed by host id:
  `{"develop-qzapp": {"leases": {"cpu": {"slots": 3, "jobs": 3}}, "cpu_weight": {"user": 400}}}`,
  with a schema. It is a separate file from registry.json because ADR-010
  rule 2 keeps that file to placement (:88-89). The heavy verbs go in
  `policies/heavy-commands.json` and the project scripts in registry.json (§2).
- **Distribution.** bootstrap.py builds heavy-bin and launch.py prepends it.
  Both arrive with `fabric-ctl all upgrade fabric`, which reruns bootstrap
  (control/upgrade.py:686). The PATH change reaches a session at its
  **next launch** only (memory note "launch-time change needs a relaunch").
  The `CPUWeight` drop-in is root's: the persist step
  (tools/fabric/provisioning/persist_accounts.py, beside the tmpfiles entry
  at :167-186), run by the operator.
- **ADR-010 amendment.** It is needed: rule 9 changes, and the quota layer
  moves from "not built" to partly built. Draft text:

  > 9a. **`cpu` is the host's compiler and test-runner cores, a counting
  > lease** of `slots` holders (runtime/hosts/resources.json), each held with
  > the parallelism capped at `jobs`. Every heavy command takes a slot: the
  > toolchain verbs in policies/heavy-commands.json through the fabric's PATH
  > shim, `tests/run.py` for every section in its own process, a project's
  > entrypoints through fabric-lease. A slot is held by the command and is
  > inherited by its children; nested calls pass through on
  > `AGENT_FABRIC_HEAVY_HELD`. `heavy` is taken before `cpu`, never after it.
  > The shim waits (default 1500 s) where fabric-lease fails fast. CI,
  > `AGENT_FABRIC_HEAVY=0` and a host with no lease directory run unleased,
  > and the shim says so.
  >
  > 9b. `full-suite` is retired into `cpu` (or kept, see open question 2).
  >
  > Layers (§2): the account quota is built as one `CPUWeight` for the
  > coordinator's slice. Per-account quotas stay unbuilt: weights share
  > scarcity and do not reduce demand.

## 7. Decision 6: rollout and measurement, with a control

1. **Baseline, before the change.** One week of what develop-qzapp already
   records:
   - load and `/proc/pressure/cpu` every 60 s, from a user timer;
   - suite wall time (run.py prints per-suite output; add one
     `elapsed=` line);
   - flakes: a red full run whose rerun is green on the same head.
2. **Control.** The same fixed workload before and after: `tests/run.sh
   python` on one pinned commit, run alone on an idle host (the lower bound),
   then together with three scripted contenders (cargo build of interweave,
   `dotnet build` of gzapp, a second run.sh), both unleased and leased. The
   numbers to read are the measured run's wall time and pass rate, and the
   total time until all four finish. Leasing should cost the measured run
   some queueing and save more in total and in reds. A result where every
   case passes means nothing without the planted contention (memory note
   "checks need a control").
3. **Ship in this order:**
   - (i) lease.py `--slots` with tests;
   - (ii) run.py takes `cpu` for every section and passes `jobs`. This alone
     covers the measured python load;
   - (iii) the shim for cargo and dotnet;
   - (iv) flutter, gradle and npm scripts, plus the CPUWeight drop-in.
   After each step, a week on develop-qzapp against the baseline, and slots
   or jobs tuned in resources.json, not in code.
4. **Exit criteria.** Load under 2×nproc at the 95th percentile, CPU pressure
   some under 60%, zero load flakes on the control, and run.sh python wall
   time within 1.5× of the idle baseline.

## 8. Decision 7: lanes

fabric-coordinator (this repository):
- lease.py `--slots` and `--who` for N slots, with tests in
  tests/test_lease.py and tests/test_fabric_lease_cli.py;
- tools/fabric/heavy.py and bin/fabric-heavy;
- bootstrap.py building heavy-bin, launch.py prepending it;
- run.py and run_python_suites.py;
- policies/heavy-commands.json and runtime/hosts/resources.json with their
  schemas;
- the persist_accounts.py drop-in;
- the ADR-010 amendment and the CLAUDE.md line on backgrounding.
  The python-dev logins can supply this on `for/` branches.

Each project's holder, in its own repository:
- gzapp's devex-tooling: Makefile targets take `cpu` after `heavy`
  (Makefile:654-671). Check that trial.json's no-lease note still holds.
- flutter/gradle: wrap `./gradlew`.
- npm/pnpm projects: name their `heavy_scripts` (a registry.json edit,
  proposed to fabric-coordinator).
- Rust projects (interweave, herdr, gateway): nothing to do unless an
  entrypoint bypasses PATH.

The operator applies the root drop-in. fleetdeck's 29 view processes (the
largest single consumer at ~120%) are a separate job for its owner. A lease
cannot help them.

## 9. Open questions for the owner

1. Should the shim wait by default (proposed: 1500 s) or fail fast like
   fabric-lease?
2. Should `full-suite` be retired into `cpu`, or kept for `all` beside a cpu
   slot? Keeping it serialises full runs host-wide, which is still the
   one-run-per-host rule j298 asked for.
3. slots=3/jobs=3 versus 2/4 to start. The first trades per-build speed for
   more concurrent agents.
4. The slot is inherited by children, so a leftover process keeps it. Is
   that the right trade, given that build servers are switched off?
5. Is `cargo check`/`clippy` heavy for every login, or exempt when the target
   directory is warm?
6. Should the coordinator slice's CPUWeight=400 come now or after step 3?

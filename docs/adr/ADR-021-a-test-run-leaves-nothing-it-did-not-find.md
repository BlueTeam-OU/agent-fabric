# ADR-021 — A test run leaves nothing it did not find

**Date:** 2026-09-19
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** identities/prompt/team.md (the rule every session reads); tests/run.sh, tests/leak-check.sh, tests/test_leak-check.sh, tests/scratch.mjs, tests/static.sh; the temporary directories of tools/fabric/assemble.py and tools/fabric/harvest_memory.py
**Pillar:** P3

## 1. Context and Problem

Every account on a developer host shares its disk, and every suite run
by every agent wrote somewhere. On 2026-09-19 the host died under two
backend suites running at once, each materialising a database schema per
test class in its own container volume (ADR-010). The next day the
coordinator's own account held 472 directories, 120 MB, under its
temporary directory — about seventy new ones per run of the fabric's own
suite, most from node suites that made a directory and never removed it,
and more from runs killed mid-way.

Nobody had looked, because a leftover is invisible to the run that left
it and costs only the next session, or the host.

## 2. Decision

**A test run leaves behind nothing it did not find**. Containers and volumes a run started are gone when it ends,
however it ends; scratch goes under the session's scratchpad, never into
the tree; a build that changed the dependency graph cleans its target,
and an incremental cache is disposable and removed when it is large —
not after every run. Measure before cleaning, and say what was removed
and how much.

In agent-fabric the rule is a check, not only a habit: `tests/run.sh`
owns a fresh temporary directory per run, exports it as `TMPDIR`, and
fails naming by path every entry the run left in it.

## 3. Alternatives Considered

- **A removal in each test's own `finally`.** The shape that was
  forgotten seventy times; the registration now happens where the
  directory is made and the removal where the process ends.
- **Clean the account's temporary directory after a run.** Rejected: it
  would remove what another run, an install or an editor wrote there at
  the same time, and it hides which suite leaked.
- **Clean every cache after every build.** Rejected by the rule itself:
  the waste is the variant graphs a dependency change leaves, not the
  cache; cleaning each run costs every next build.

## 4. Rationale

Consuming a shared resource is a cooperative act (ADR-000, P7), and a
commitment one agent makes to the others on the host (P3). A leak made a
failure named by path turns an invisible cost into a red suite on the
branch that caused it, where it is cheapest to fix.

## 5. Binding Rules

1. A test run removes, however it ends, the containers, volumes and
   scratch it created; nothing it creates goes into the working tree.
2. `tests/run.sh` makes a new directory under the account's temporary
   directory for the run, exports it as `TMPDIR`, removes it on exit
   (a signal exits, and the exit removes), and before that fails the run
   naming every entry left in it (`tests/leak-check.sh`;
   `tests/test_leak-check.sh` plants one to prove it fires).
3. A node suite makes its temporary directories through
   `scratch()` from `tests/scratch.mjs`, which removes them at process
   exit and on SIGINT, SIGTERM and SIGHUP; `tests/static.sh` refuses an
   inline `mkdtempSync` in a `*.test.mjs`. A Python tool or suite
   registers the removal of its temporary directory where it makes it
   (`atexit`, or a `TemporaryDirectory`).
4. A leftover a run names is fixed at the rule level in the suite that
   made it — a helper or an exit hook — not by a one-off removal.
5. A build that changed the dependency graph cleans its target; a large
   incremental cache is removed; neither is cleaned after every run.
   Whoever cleans measures first and says what was removed and how much.

## 6. Consequences

- A suite that leaks fails the fabric's CI, on every leg that runs
  `tests/run.sh`.
- Because each run owns its directory, a second run, an install or an
  editor writing into the account's temporary directory at the same
  time is never counted as a leak. The earlier advice never to run the
  suite twice at once (the two shared scratch) predates that change
  (8898a5d, 2026-09-20); whether any suite still shares other state
  between concurrent runs is not established.
- Rules 1 and 5 in a managed project are that project's suites to keep;
  the fabric supplies the host lease that serialises memory-heavy runs
  (ADR-010), not a leak check for them.

## 7. Future Evolution

None stated. A managed project that wants the same check can take the
shape of `tests/run.sh` and `tests/leak-check.sh`.

## 8. Decision Status

Accepted: the owner's rule of 2026-09-19 in `team.md`; the fabric's leak
check since 2026-09-20 (agent-fabric #26).

## References

- `identities/prompt/team.md` ("A test run leaves behind nothing it did
  not find").
- `tests/run.sh`, `tests/leak-check.sh`, `tests/test_leak-check.sh`,
  `tests/scratch.mjs`, `tests/static.sh`.
- `.agent-fabric/memory/fabric-coordinator/threads/suite-scratch-leak.md`
  (the measurement of 2026-09-20).
- `docs/live-checks/2026-09-19-develop-qzapp-crash.md`; ADR-010 (the host
  lease), ADR-000 (P3, P7).

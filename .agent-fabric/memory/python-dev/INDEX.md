---
role: "python-dev"
class: index
description: "What python-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-05"
---

# python-dev — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/python-dev/charter.md`](identities/roles/python-dev/charter.md) — The fleet's Python developer: command-line tools, services and their tests, written to a frozen contract on the standard library, and the port of shell scripts to Python with the old tests as the parity oracle.

## brief

- [`identities/roles/python-dev/brief.md`](identities/roles/python-dev/brief.md) — How python-dev works day to day, in any project: freeze the contract, keep boundaries and failure explicit, prove the oracle can fail, verify the real invocation path, deliver evidence by level.

## domain

- [`memory/domains/python-dev/domain/env-isolation-in-process-environ.md`](memory/domains/python-dev/domain/env-isolation-in-process-environ.md) — an oracle's git/env isolation set in a filtered env dict misses fixture calls that pass no env=; set it in os.environ and prove it with a hostile caller config
- [`memory/domains/python-dev/domain/facade-split-monkeypatch-trap.md`](memory/domains/python-dev/domain/facade-split-monkeypatch-trap.md) — before splitting a Python module behind a re-exporting facade, find every patch of its attributes — including inside subprocess code strings and by-path loads
- [`memory/domains/python-dev/domain/git-config-get-reads-beyond-the-repo.md`](memory/domains/python-dev/domain/git-config-get-reads-beyond-the-repo.md) — Reading trust state from a repo's .git/config — a plain `git config --get` also reads ~/.gitconfig, system and GIT_CONFIG_* env; use --local
- [`memory/domains/python-dev/domain/oracle-blind-spots-in-ports.md`](memory/domains/python-dev/domain/oracle-blind-spots-in-ports.md) — Porting a script with its old test as the oracle — the shapes of mutation an oracle passes, and how each was pinned
- [`memory/domains/python-dev/domain/python-defaults-that-differ-from-node.md`](memory/domains/python-dev/domain/python-defaults-that-differ-from-node.md) — porting Node to Python — the stdlib defaults that silently differ (Unicode \d, or vs ??, urllib proxy/redirect, header CRLF errors, stdout encoding)

## solution

- [`.agent-fabric/memory/python-dev/solution/gzcoord-tests-reach-the-host-workspace.md`](.agent-fabric/memory/python-dev/solution/gzcoord-tests-reach-the-host-workspace.md) — GZCoord command tests read the real projects/.gzcoord unless AGENT_FABRIC_ROOT points at a scratch workspace; green on a non-hosting account proves nothing
- [`.agent-fabric/memory/python-dev/solution/root-relative-tools-write-the-running-clone.md`](.agent-fabric/memory/python-dev/solution/root-relative-tools-write-the-running-clone.md) — a test that runs a tool finding its root from its own path (bootstrap.sh) writes the clone running the suite; invisible under projects/, seen only from a scratch clone
- [`.agent-fabric/memory/python-dev/solution/store-rerun-after-put-pushes-stale-head.md`](.agent-fabric/memory/python-dev/solution/store-rerun-after-put-pushes-stale-head.md) — Any secret-store path that pushes a head it built from the account's side (store push, seed-child's clone) must fast-forward to the remote first — the parent's puts make it behind
- [`.agent-fabric/memory/shared/solution-gnupghome-default-agent-trap.md`](.agent-fabric/memory/shared/solution-gnupghome-default-agent-trap.md) — A test GNUPGHOME equal to $HOME/.gnupg shares the account's REAL gpg-agent — scratch keys land in ~/.gnupg and "separate" keyrings decrypt each other (shared)

## rationale

- [`.agent-fabric/memory/python-dev/rationale.md`](.agent-fabric/memory/python-dev/rationale.md) — ADR-042 (signed store commits) — the coordinator's three rulings of 2026-10-04 that shape secret_store.py; read before touching store verification

## workflow

- [`.agent-fabric/memory/python-dev/workflow/check-authority-excluding-before-planning.md`](.agent-fabric/memory/python-dev/workflow/check-authority-excluding-before-planning.md) — before planning code on a control-plane path, read python-dev's "excluding" in policies/authority.json — an assignment does not admit the path
- [`.agent-fabric/memory/python-dev/workflow/contributor-merge-direction.md`](.agent-fabric/memory/python-dev/workflow/contributor-merge-direction.md) — merging an older fix branch into a contributor branch that already folded main is refused by contributors.py; merge with the fix as first parent instead
- [`.agent-fabric/memory/python-dev/workflow/fake-tools-must-sit-on-the-callees-path.md`](.agent-fabric/memory/python-dev/workflow/fake-tools-must-sit-on-the-callees-path.md) — Faking a tool for code that builds its own PATH (env -i, a login shell, sudo) — the fake must sit where THAT PATH looks first, or the host's real tool answers and the test is green for the wrong reason
- [`.agent-fabric/memory/python-dev/workflow/lint-in-a-worktree-reads-the-session-root.md`](.agent-fabric/memory/python-dev/workflow/lint-in-a-worktree-reads-the-session-root.md) — tools/fabric/lint.py run from a contributor worktree with the session's AGENT_FABRIC_ROOT lints ~/projects/agent-fabric (main), not the worktree — a green "lint clean" that is not about your branch
- [`.agent-fabric/memory/python-dev/workflow/suites-inherit-launch-stamps.md`](.agent-fabric/memory/python-dev/workflow/suites-inherit-launch-stamps.md) — Running a suite "as CI" — strip CLAUDE_* and ANTHROPIC_* as well as AGENT_FABRIC_*/GITHUB_*/GIT_DIR; a launched session's own exports satisfy assertions CI would fail
- [`.agent-fabric/memory/python-dev/workflow/test-port-by-mutation-parity.md`](.agent-fabric/memory/python-dev/workflow/test-port-by-mutation-parity.md) — Porting a bash TEST to Python has no oracle of its own — prove it by planting mutations in the implementation that both suites must fail; how to run that without losing hours
- [`.agent-fabric/memory/shared/workflow-check-exit-status-not-pipe.md`](.agent-fabric/memory/shared/workflow-check-exit-status-not-pipe.md) — Never `check | tail -1 && git commit`: the pipe's status is tail's, so a failed lint/static/suite still commits — run the check, capture rc=$?, commit only on 0 (shared)
- [`.agent-fabric/memory/shared/workflow-guard-must-catch-the-shape-it-replaced.md`](.agent-fabric/memory/shared/workflow-guard-must-catch-the-shape-it-replaced.md) — A guard added alongside a fix is verified by planting the exact shape the fix removed — not the shape you had in mind when you wrote the pattern (shared)
- [`.agent-fabric/memory/shared/workflow-local-grep-is-ugrep.md`](.agent-fabric/memory/shared/workflow-local-grep-is-ugrep.md) — On develop-qzapp `grep` resolves to ugrep — tests/static.sh's sh-shebang check passed locally and failed in CI; verify a grep-based guard with /usr/bin/grep before trusting a local green (shared)
- [`.agent-fabric/memory/shared/workflow-prefer-python-over-shell.md`](.agent-fabric/memory/shared/workflow-prefer-python-over-shell.md) — owner 2026-09-29 — write new fabric tooling (and non-trivial ad-hoc logic) in Python, not shell scripts (shared)
- [`.agent-fabric/memory/shared/workflow-run-suites-as-ci-before-push.md`](.agent-fabric/memory/shared/workflow-run-suites-as-ci-before-push.md) — A suite green in a launched session can fail in CI — the session sets AGENT_FABRIC_ROOT, CI's pull_request sets GITHUB_HEAD_REF/BASE_REF; run the touched suites with CI's environment before pushing (shared)
- [`.agent-fabric/memory/shared/workflow-smoke-container-before-ci.md`](.agent-fabric/memory/shared/workflow-smoke-container-before-ci.md) — Run a platform smoke job under podman on this host, as an unprivileged login, before pushing a CI change that adds a container job — the containers find host facts (a missing cmp, Debian's /etc/profile resetting PATH, dash as sh) that the… (shared)
- [`.agent-fabric/memory/shared/workflow-worktree-under-dot-claude.md`](.agent-fabric/memory/shared/workflow-worktree-under-dot-claude.md) — an isolated subagent's worktree lives in <repo>/.claude/worktrees/; `git add -A` in the main checkout stages it as an embedded repo (shared)

## threads

- [`.agent-fabric/memory/python-dev/threads/j24-signing-key-off-env-findings.md`](.agent-fabric/memory/python-dev/threads/j24-signing-key-off-env-findings.md) — j24 (signing key off the environment; agentd memory sampling) — what was built, on which branch, and what is left for the coordinator
- [`.agent-fabric/memory/python-dev/threads/wave-7-port-state.md`](.agent-fabric/memory/python-dev/threads/wave-7-port-state.md) — ADR-040 Wave 7 port (gzmsg/send/inbox/i18n to Python) — LANDED in #93 (2026-10-04); the decisions it took (presence via a Node CLI, the oracle rules)
- [`.agent-fabric/memory/shared/threads-python-port-waves.md`](.agent-fabric/memory/shared/threads-python-port-waves.md) — owner-approved plan (2026-09-29) to port the fabric's ~10.5k lines of production bash to Python in waves; jobs j3–j9; ADR-040 in Wave 0 (shared)
- [`.agent-fabric/memory/shared/threads-suite-scratch-leak.md`](.agent-fabric/memory/shared/threads-suite-scratch-leak.md) — tests/run.sh fails naming anything a run left under TMPDIR (since agent-fabric #26, 2026-09-20); node suites use tests/scratch.mjs, static.sh refuses inline mkdtempSync; never run the suite twice at once — the two share scratch and fail… (shared)

## recall

- [`identities/roles/python-dev/recall.md`](identities/roles/python-dev/recall.md) — Where python-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.

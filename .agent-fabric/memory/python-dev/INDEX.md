---
role: "python-dev"
class: index
description: "What python-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-01"
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

## solution

- [`.agent-fabric/memory/shared/solution-gnupghome-default-agent-trap.md`](.agent-fabric/memory/shared/solution-gnupghome-default-agent-trap.md) — A test GNUPGHOME equal to $HOME/.gnupg shares the account's REAL gpg-agent — scratch keys land in ~/.gnupg and "separate" keyrings decrypt each other (shared)

## workflow

- [`.agent-fabric/memory/shared/workflow-check-exit-status-not-pipe.md`](.agent-fabric/memory/shared/workflow-check-exit-status-not-pipe.md) — Never `check | tail -1 && git commit`: the pipe's status is tail's, so a failed lint/static/suite still commits — run the check, capture rc=$?, commit only on 0 (shared)
- [`.agent-fabric/memory/shared/workflow-guard-must-catch-the-shape-it-replaced.md`](.agent-fabric/memory/shared/workflow-guard-must-catch-the-shape-it-replaced.md) — A guard added alongside a fix is verified by planting the exact shape the fix removed — not the shape you had in mind when you wrote the pattern (shared)
- [`.agent-fabric/memory/shared/workflow-local-grep-is-ugrep.md`](.agent-fabric/memory/shared/workflow-local-grep-is-ugrep.md) — On develop-qzapp `grep` resolves to ugrep — tests/static.sh's sh-shebang check passed locally and failed in CI; verify a grep-based guard with /usr/bin/grep before trusting a local green (shared)
- [`.agent-fabric/memory/shared/workflow-prefer-python-over-shell.md`](.agent-fabric/memory/shared/workflow-prefer-python-over-shell.md) — owner 2026-09-29 — write new fabric tooling (and non-trivial ad-hoc logic) in Python, not shell scripts (shared)
- [`.agent-fabric/memory/shared/workflow-run-suites-as-ci-before-push.md`](.agent-fabric/memory/shared/workflow-run-suites-as-ci-before-push.md) — A suite green in a launched session can fail in CI — the session sets AGENT_FABRIC_ROOT, CI's pull_request sets GITHUB_HEAD_REF/BASE_REF; run the touched suites with CI's environment before pushing (shared)
- [`.agent-fabric/memory/shared/workflow-smoke-container-before-ci.md`](.agent-fabric/memory/shared/workflow-smoke-container-before-ci.md) — Run a platform smoke job under podman on this host, as an unprivileged login, before pushing a CI change that adds a container job — the containers find host facts (a missing cmp, Debian's /etc/profile resetting PATH, dash as sh) that the… (shared)
- [`.agent-fabric/memory/shared/workflow-worktree-under-dot-claude.md`](.agent-fabric/memory/shared/workflow-worktree-under-dot-claude.md) — an isolated subagent's worktree lives in <repo>/.claude/worktrees/; `git add -A` in the main checkout stages it as an embedded repo (shared)

## threads

- [`.agent-fabric/memory/shared/threads-python-port-waves.md`](.agent-fabric/memory/shared/threads-python-port-waves.md) — owner-approved plan (2026-09-29) to port the fabric's ~10.5k lines of production bash to Python in waves; jobs j3–j9; ADR-040 in Wave 0 (shared)
- [`.agent-fabric/memory/shared/threads-suite-scratch-leak.md`](.agent-fabric/memory/shared/threads-suite-scratch-leak.md) — tests/run.sh fails naming anything a run left under TMPDIR (since agent-fabric #26, 2026-09-20); node suites use tests/scratch.mjs, static.sh refuses inline mkdtempSync; never run the suite twice at once — the two share scratch and fail… (shared)

## recall

- [`identities/roles/python-dev/recall.md`](identities/roles/python-dev/recall.md) — Where python-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.

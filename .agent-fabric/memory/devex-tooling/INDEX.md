---
role: "devex-tooling"
class: index
description: "What devex-tooling knows and where it lives."
tier: 1
distilled_at: "2026-10-18"
---

# devex-tooling — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/devex-tooling/charter.md`](identities/roles/devex-tooling/charter.md) — The machinery everyone works inside: the agent harness, the forge, repo tooling, branch and commit discipline, the local development stack.

## brief

- [`identities/roles/devex-tooling/brief.md`](identities/roles/devex-tooling/brief.md) — How devex-tooling works day to day, in any project: keeps the machinery every other session works inside honest — the local stack, the forge tooling, the guards, the harness wiring, the host docs.

## domain

- [`memory/domains/devex-tooling/domain/amend-records-only-staged-changes.md`](memory/domains/devex-tooling/domain/amend-records-only-staged-changes.md) — git commit --amend -F - without -a re-records the message only; an edit made after the commit stays unstaged — check git status before pushing an amend
- [`memory/domains/devex-tooling/domain/aot-snapshot-byte-find-needs-a-positive-control.md`](memory/domains/devex-tooling/domain/aot-snapshot-byte-find-needs-a-positive-control.md) — A byte-find on a Flutter release snapshot (libapp.so) passes on an --obfuscate build because the names are gone; require a control string that only an unobfuscated snapshot carries.
- [`memory/domains/devex-tooling/domain/bash-scripting-pitfalls.md`](memory/domains/devex-tooling/domain/bash-scripting-pitfalls.md) — bash's command_not_found_handle runs in a subshell (5.3+) — a counter-based self-test guard built on it is silently vacuous
- [`memory/domains/devex-tooling/domain/bash-signal-cleanup-traps.md`](memory/domains/devex-tooling/domain/bash-signal-cleanup-traps.md) — Writing cleanup for a CI shell script, or a self-test that signals one: EXIT trap suffices for INT/TERM; & jobs start with INT ignored
- [`memory/domains/devex-tooling/domain/cargo-machete-dev-deps-and-silent-fallback.md`](memory/domains/devex-tooling/domain/cargo-machete-dev-deps-and-silent-fallback.md) — cargo-machete 0.9.2: default mode never reads [dev-dependencies]; --with-metadata does, but exits 0 silently when cargo metadata fails — resolve metadata yourself first
- [`memory/domains/devex-tooling/domain/claude-code-bash-permission-matcher.md`](memory/domains/devex-tooling/domain/claude-code-bash-permission-matcher.md) — Claude Code's Bash permission matcher is a text-pattern system with specific, repeatedly-rediscovered bypass and false-safety classes
- [`memory/domains/devex-tooling/domain/claude-github-app-billing.md`](memory/domains/devex-tooling/domain/claude-github-app-billing.md) — Claude/Anthropic GitHub Actions installed via /install-github-app bill the subscription
- [`memory/domains/devex-tooling/domain/deps-only-cargo-cache-measure-first.md`](memory/domains/devex-tooling/domain/deps-only-cargo-cache-measure-first.md) — before proposing a cargo cache in CI, measure how much of the build is dependencies — cargo clean -p every workspace package and rebuild
- [`memory/domains/devex-tooling/domain/fabric-lint-is-not-in-run-sh.md`](memory/domains/devex-tooling/domain/fabric-lint-is-not-in-run-sh.md) — correction — agent-fabric tests/run.sh does run tools/fabric/lint.py ("corpus lint"); only a narrower section skips it
- [`memory/domains/devex-tooling/domain/fast-clock-through-bash-env.md`](memory/domains/devex-tooling/domain/fast-clock-through-bash-env.md) — Speed up a bash suite whose script under test naps on a wall-clock SECONDS deadline — source a sleep() through BASH_ENV that ages SECONDS, keep real latency on `command sleep`, and prove the clock is live with a control case.
- [`memory/domains/devex-tooling/domain/find-is-bfs-not-gnu-findutils.md`](memory/domains/devex-tooling/domain/find-is-bfs-not-gnu-findutils.md) — `find` on develop-qzapp is bfs, which rejects relative timestamps — and the error reads as "zero results" whenever stderr is discarded.
- [`memory/domains/devex-tooling/domain/gh-merge-fails-but-merges.md`](memory/domains/devex-tooling/domain/gh-merge-fails-but-merges.md) — gh pr merge can exit non-zero while GitHub merges the PR, and the PR API then lags (OPEN, DIRTY) for minutes; ask git whether the head is in the base
- [`memory/domains/devex-tooling/domain/gh-pr-merge-strategy-flag-on-a-queued-repo.md`](memory/domains/devex-tooling/domain/gh-pr-merge-strategy-flag-on-a-queued-repo.md) — `gh pr merge --auto --merge` on gzapp prints what looks like a refusal, leaves autoMergeRequest null, yet DOES enqueue the PR.
- [`memory/domains/devex-tooling/domain/gh-rerun-keeps-workflow-snapshot.md`](memory/domains/devex-tooling/domain/gh-rerun-keeps-workflow-snapshot.md) — re-running a failed GitHub Actions job replays the run's old workflow file; after a workflow fix on main, a PR needs a fresh run (update the branch), not a re-run
- [`memory/domains/devex-tooling/domain/github-actions-billing.md`](memory/domains/devex-tooling/domain/github-actions-billing.md) — A nonzero Actions netAmount (filtered to the Minutes SKU) means overage IS being purchased and runners ARE still dispatching — not that the allowance is spent
- [`memory/domains/devex-tooling/domain/github-actions-reusable-workflows.md`](memory/domains/devex-tooling/domain/github-actions-reusable-workflows.md) — Inside a reusable workflow, github.event_name is the CALLING workflow's event; a gate that skips on an unlisted event can turn a release gate green with nothing built
- [`memory/domains/devex-tooling/domain/github-runner-unprivileged-userns.md`](memory/domains/devex-tooling/domain/github-runner-unprivileged-userns.md) — ubuntu-latest (24.04) blocks `unshare -r` via AppArmor; one sysctl lifts it, and a dummy link inside the netns needs no modprobe — measured 2026-09-25
- [`memory/domains/devex-tooling/domain/grep-q-pipefail-silent-pass.md`](memory/domains/devex-tooling/domain/grep-q-pipefail-silent-pass.md) — In a guard under set -o pipefail, never end a pipe in grep -q -- its early exit SIGPIPEs the writer and a match reads as a miss
- [`memory/domains/devex-tooling/domain/harness-param-accepted-is-not-honoured.md`](memory/domains/devex-tooling/domain/harness-param-accepted-is-not-honoured.md) — a Claude Code tool parameter a skill or decision names may be absent, rejected or silently ignored in this build or session mode; read the schema you hold and what the tool answers
- [`memory/domains/devex-tooling/domain/make-recursive-line-runs-under-dry-run.md`](memory/domains/devex-tooling/domain/make-recursive-line-runs-under-dry-run.md) — a recipe line that references $(MAKE) RUNS under make -n — a callback string carrying $(MAKE) made `make -n tiles-publish` publish a real vintage
- [`memory/domains/devex-tooling/domain/make-shell-arguments-cannot-hold-unbalanced-parens.md`](memory/domains/devex-tooling/domain/make-shell-arguments-cannot-hold-unbalanced-parens.md) — A `case … *)` (or any unbalanced `)`) inside a Makefile $(shell …) ends the call early and the rest of the text becomes the value; and a value substituted into a $(shell bash -c '…') string is shell text at parse time on every make.
- [`memory/domains/devex-tooling/domain/npm-ci-scripts.md`](memory/domains/devex-tooling/domain/npm-ci-scripts.md) — npm run --if-present silently no-ops — dangerous for a script that's the only check of something
- [`memory/domains/devex-tooling/domain/podman-cli-quirks.md`](memory/domains/devex-tooling/domain/podman-cli-quirks.md) — Podman has non-obvious quirks in non-interactive local-dev workflows
- [`memory/domains/devex-tooling/domain/podman-lock-collision-deadlocks-start-after-reboot.md`](memory/domains/devex-tooling/domain/podman-lock-collision-deadlocks-start-after-reboot.md) — after a VM reboot, `podman start` (and then every podman ps/stats) hung on a futex — the compose pod and a volume shared lock 0; `podman system renumber` fixes it
- [`memory/domains/devex-tooling/domain/popen-closed-stdin-communicate-py313.md`](memory/domains/devex-tooling/domain/popen-closed-stdin-communicate-py313.md) — a test that writes Popen stdin, closes it by hand, then calls communicate() raises ValueError on Python 3.13 (CI) though it passes on 3.14 locally
- [`memory/domains/devex-tooling/domain/postgres-image-layout.md`](memory/domains/devex-tooling/domain/postgres-image-layout.md) — Postgres 18+ images moved the data directory under a version subdirectory
- [`memory/domains/devex-tooling/domain/pretooluse-guard-cannot-enumerate-deny.md`](memory/domains/devex-tooling/domain/pretooluse-guard-cannot-enumerate-deny.md) — A custom PreToolUse hook that DENIES known-bad text shapes and stays silent otherwise fails open, not closed — it needs the opposite polarity
- [`memory/domains/devex-tooling/domain/setup-python-replaces-the-jobs-python3.md`](memory/domains/devex-tooling/domain/setup-python-replaces-the-jobs-python3.md) — actions/setup-python puts its python3 first for every later step; suites needing the runner's modules (PyYAML) break — use update-environment false and a per-suite PATH
- [`memory/domains/devex-tooling/domain/splitlines-rejoin-rewrites-breaks.md`](memory/domains/devex-tooling/domain/splitlines-rejoin-rewrites-breaks.md) — Python str.splitlines breaks at U+2028/U+2029/U+0085/\x0b/\x0c/\x1c-\x1e too; filter lines with keepends=True and join "", never rejoin with "\n"
- [`memory/domains/devex-tooling/domain/subagent-transcript-shape.md`](memory/domains/devex-tooling/domain/subagent-transcript-shape.md) — what a Claude Code subagent transcript shows about how the run ended, cost and effort (read 2026-10-14 over 348 transcripts on develop-qzapp)
- [`memory/domains/devex-tooling/domain/sudo-i-leaves-dollar-live-in-the-target-shell.md`](memory/domains/devex-tooling/domain/sudo-i-leaves-dollar-live-in-the-target-shell.md) — sudo -i with a command re-escapes the argv for the target login shell but leaves $ unescaped, so any "$1"/"$VAR" in the command expands in that shell (empty) — never pass a $-bearing argument under -i.
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## solution

- [`.agent-fabric/memory/devex-tooling/solution/gzapp-ci-artifacts-and-gradle-cache.md`](.agent-fabric/memory/devex-tooling/solution/gzapp-ci-artifacts-and-gradle-cache.md) — gzapp Actions storage audit: unexpired artifacts are retention, not a leak; Gradle caches look unread but are weekly by design; a cancelled shard still runs a cancelled()-guarded step
- [`.agent-fabric/memory/devex-tooling/solution/interweave-moved-to-blueteam-ou.md`](.agent-fabric/memory/devex-tooling/solution/interweave-moved-to-blueteam-ou.md) — InterWeave lives at BlueTeam-OU since 2026-10-12, client blueteam; gh API writes through gzapi-org/InterWeave fail with HTTP 307
- [`.agent-fabric/memory/devex-tooling/solution/narrowed-path-suite-needs-fabric-root.md`](.agent-fabric/memory/devex-tooling/solution/narrowed-path-suite-needs-fabric-root.md) — a gzapp suite that runs a fabric hand-over on a narrowed PATH must resolve and export AGENT_FABRIC_ROOT first, or a local CI-env run differs from CI
- [`.agent-fabric/memory/devex-tooling/solution/ots-signing-flaky-retry.md`](.agent-fabric/memory/devex-tooling/solution/ots-signing-flaky-retry.md) — git commit fails "ots: need at least 2 attestations" — the OpenTimestamps calendars are slow, retry the commit
- [`.agent-fabric/memory/devex-tooling/solution/proc-scan-not-atomic-against-fork.md`](.agent-fabric/memory/devex-tooling/solution/proc-scan-not-atomic-against-fork.md) — killing a check's leftovers by a /proc scan (by session or cwd) misses a child forked mid-scan; rescan until no one new — trial-merge lease flake j128
- [`.agent-fabric/memory/devex-tooling/solution/rollup-keeps-superseded-runs.md`](.agent-fabric/memory/devex-tooling/solution/rollup-keeps-superseded-runs.md) — statusCheckRollup.contexts lists every check run on a head, cancelled/re-run ones too; read the latest per check
- [`.agent-fabric/memory/devex-tooling/solution/settings-validate-test-env.md`](.agent-fabric/memory/devex-tooling/solution/settings-validate-test-env.md) — agent-fabric-settings tools/test_validate_policies.py exits 1 without FABRIC and SETTINGS_REPO=<owner>/<name>
- [`.agent-fabric/memory/devex-tooling/solution/solution-carried-2026-10-12.md`](.agent-fabric/memory/devex-tooling/solution/solution-carried-2026-10-12.md) — tests/run.sh in agent-fabric reports test_gzcoord_compose FAILED when run as the devex-tooling login — pre-existing, not a regression

## workflow

- [`.agent-fabric/memory/devex-tooling/workflow/agent-fabric-arm-json-outside-entry.md`](.agent-fabric/memory/devex-tooling/workflow/agent-fabric-arm-json-outside-entry.md) — projects/agent-fabric/integration/gh/arm.json is NOT in devex-tooling's authority entry (only gzapp's and interweave's are); and the fence refuses any non-for/ branch name
- [`.agent-fabric/memory/devex-tooling/workflow/cli-suite-audit-pattern.md`](.agent-fabric/memory/devex-tooling/workflow/cli-suite-audit-pattern.md) — how to cut a slow agent-fabric CLI test suite to smoke cases without losing a contract, and the trap a blind review caught
- [`.agent-fabric/memory/devex-tooling/workflow/contract-test-renders-real-producer.md`](.agent-fabric/memory/devex-tooling/workflow/contract-test-renders-real-producer.md) — a test that a reader takes every field a producer writes must feed the producer's output verbatim, every value set, and assert every key — never re-inject the key under test
- [`.agent-fabric/memory/devex-tooling/workflow/fabric-agent-store-never-by-hand.md`](.agent-fabric/memory/devex-tooling/workflow/fabric-agent-store-never-by-hand.md) — Never clone or push my fabric-agent-<id> repo by hand, nor hand the owner a script that does; settings go through fabric-secrets store settings-put
- [`.agent-fabric/memory/devex-tooling/workflow/fence-refuses-amend.md`](.agent-fabric/memory/devex-tooling/workflow/fence-refuses-amend.md) — the agent-fabric contributor fence refuses git commit --amend (no path staged); redo an unpushed commit with reset --soft HEAD~1 and a new commit
- [`.agent-fabric/memory/devex-tooling/workflow/jobs-reply-artifact-names-request.md`](.agent-fabric/memory/devex-tooling/workflow/jobs-reply-artifact-names-request.md) — fabric-jobs artifact reply:<id> names the message answered (IN-REPLY-TO), not your reply's own id; artifacts are append-only
- [`.agent-fabric/memory/devex-tooling/workflow/launch-cli-gateway-timeout-flake.md`](.agent-fabric/memory/devex-tooling/workflow/launch-cli-gateway-timeout-flake.md) — test_launch_cli (groups 6, 8) and test_gzcoord_protocol can FAIL in a full tests/run.sh under load and pass alone, at base too
- [`.agent-fabric/memory/devex-tooling/workflow/lint-no-siblings-for-own-tree.md`](.agent-fabric/memory/devex-tooling/workflow/lint-no-siblings-for-own-tree.md) — tools/fabric/lint.py reports sibling projects' memory-index drift; --no-siblings is the clean check of agent-fabric's own tree
- [`.agent-fabric/memory/devex-tooling/workflow/outside-entry-supply-as-staged-diff.md`](.agent-fabric/memory/devex-tooling/workflow/outside-entry-supply-as-staged-diff.md) — a supply outside my authority entry cannot be committed, so no format-patch; stage it in a worktree, review INDEX..WORKTREE, send git diff --binary + message
- [`.agent-fabric/memory/devex-tooling/workflow/presence-check-needs-content-evidence.md`](.agent-fabric/memory/devex-tooling/workflow/presence-check-needs-content-evidence.md) — a skip, "already done" or input-present check must test the content the step produces (non-empty file, the rows it fills), never a marker or path an older or other producer can leave
- [`.agent-fabric/memory/devex-tooling/workflow/review-brief-json-request.md`](.agent-fabric/memory/devex-tooling/workflow/review-brief-json-request.md) — fabric-review brief takes a JSON request (no render verb); card_base when the base is off main, previous_findings for a re-review, fixed lens names
- [`.agent-fabric/memory/devex-tooling/workflow/review-class-cannot-read-scratchpad-diff.md`](.agent-fabric/memory/devex-tooling/workflow/review-class-cannot-read-scratchpad-diff.md) — A review brief's diff file in the session scratchpad is refused to the review class; hunks only in a patch go unreviewed
- [`.agent-fabric/memory/devex-tooling/workflow/review-class-leaves-run-user-scratch.md`](.agent-fabric/memory/devex-tooling/workflow/review-class-leaves-run-user-scratch.md) — a code-review dispatch that exports trees for mutation runs cannot delete them; the session removes /run/user/<uid>/rv.*
- [`.agent-fabric/memory/devex-tooling/workflow/role-tools-on-qubes-host.md`](.agent-fabric/memory/devex-tooling/workflow/role-tools-on-qubes-host.md) — how a role's extra host tools (not the fabric's host contract) get onto develop-qzapp, and who has to run the install
- [`.agent-fabric/memory/devex-tooling/workflow/run-python-suites-names-no-failure.md`](.agent-fabric/memory/devex-tooling/workflow/run-python-suites-names-no-failure.md) — tests/run.sh python prints only FAILED_SUITES=<n>, never which suites; find them from the "== <suite>" blocks, then compare against the base
- [`.agent-fabric/memory/devex-tooling/workflow/test-arm-policy-outside-entry.md`](.agent-fabric/memory/devex-tooling/workflow/test-arm-policy-outside-entry.md) — Which agent-fabric tests of tools/fabric/github/ code are outside devex-tooling's authority entry (test_wait_merged.py is; test_arm_policy.py, and test_fabric_pr.py + test_pr_counts.py from 0cae803a, are in); an outside hunk goes to…

## threads

- [`.agent-fabric/memory/devex-tooling/threads/ci-cache-audit-thread.md`](.agent-fabric/memory/devex-tooling/threads/ci-cache-audit-thread.md) — j142 CI cache audit, open as of 2026-10-18: gateway #67 warm-run measurement owed, herdr handed to rust-ui-dev j106, InterWeave android caches wait on CodeQL expiry
- [`.agent-fabric/memory/devex-tooling/threads/j146-pr-repo-flag-design.md`](.agent-fabric/memory/devex-tooling/threads/j146-pr-repo-flag-design.md) — j146 fabric-pr --repo design survey: where each verb reads repo and project from the cwd, what to reuse, the worktree/branch already set up

## recall

- [`identities/roles/devex-tooling/recall.md`](identities/roles/devex-tooling/recall.md) — Where devex-tooling's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.

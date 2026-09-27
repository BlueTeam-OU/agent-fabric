---
role: "fabric-coordinator"
class: index
description: "What fabric-coordinator knows and where it lives."
tier: 1
distilled_at: "2026-09-27"
---

# fabric-coordinator — knowledge index

Tier 1 — the charter and brief (in the launch prompt), this index
and every `workflow` slice (from the session-start hook) — is given
to a session at start. Every other section waits for a cue: open a
slice when its description matches what you are working on.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/fabric-coordinator/charter.md`](identities/roles/fabric-coordinator/charter.md) — Owns the control plane: agent-fabric's role definitions, catalogue, routing policy, authority rules and the GZCoord protocol; the only role that changes what other roles are.

## brief

- [`identities/roles/fabric-coordinator/brief.md`](identities/roles/fabric-coordinator/brief.md) — How fabric-coordinator works day to day: the control plane's only writer — roles, routing, policy, the protocol, the launch — changed in small verified commits, distributed to every account, never project truth.

## domain

- [`memory/domains/fabric-coordinator/domain/locale-suffixes.md`](memory/domains/fabric-coordinator/domain/locale-suffixes.md) — The fabric's locale suffixes: ge is Georgian (language-culture-ge, script Georgian), ru Russian; German would be de — never read ge as German
- [`memory/domains/fabric-coordinator/domain/slice-correction-attribution-writer-name.md`](memory/domains/fabric-coordinator/domain/slice-correction-attribution-writer-name.md) — Correction for memory/shared/domain-claude-code-attribution-reminder.md: the writer bootstrap.sh runs is runtime/claude-code/user-settings.py (attribution-off.py until 2026-09-20), and it also sets showThinkingSummaries and verbose
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — Where Claude Code's Co-Authored-By / Generated-with reminder comes from, what switches it off, and what a session that still sees one means (shared)

## solution

- [`.agent-fabric/memory/fabric-coordinator/solution/assemble-not-idempotent-over-same-drain.md`](.agent-fabric/memory/fabric-coordinator/solution/assemble-not-idempotent-over-same-drain.md) — FIXED 2026-09-20: assemble is idempotent over the same drain — split_by_budget no longer counts a re-rendered claim twice (heading+text identity); the -2 copies of 2026-09-17 were the carried count doubling past half budget
- [`.agent-fabric/memory/fabric-coordinator/solution/claude-setup-token-facts.md`](.agent-fabric/memory/fabric-coordinator/solution/claude-setup-token-facts.md) — What a `claude setup-token` token can and cannot do, how to tell which account it belongs to, and that CLAUDE_CODE_OAUTH_TOKEN beats a stored sign-in — measured 2026-09-24 on 2.1.281
- [`.agent-fabric/memory/fabric-coordinator/solution/control-plane-daemon.md`](.agent-fabric/memory/fabric-coordinator/solution/control-plane-daemon.md) — Fleet facts in real time come from bin/fabric-ctl (a daemon per account on the relay's fabric:control channel), not from sudo loops; what to know when one account stays silent
- [`.agent-fabric/memory/fabric-coordinator/solution/effort-precedence-chain.md`](.agent-fabric/memory/fabric-coordinator/solution/effort-precedence-chain.md) — How Claude Code resolves reasoning effort, read out of the 2.1.280 binary — the order, the escape values, and where each level can be read back
- [`.agent-fabric/memory/fabric-coordinator/solution/fleet-upgrade-concurrency.md`](.agent-fabric/memory/fabric-coordinator/solution/fleet-upgrade-concurrency.md) — fabric-ctl all upgrade claude run on 13 accounts of one host at once: 9 installs failed; one at a time every one succeeded — serialize installs per host (fabric-lease), keep the error's LAST line, exit 1 on any failure
- [`.agent-fabric/memory/fabric-coordinator/solution/subagent-tools-and-transcripts.md`](.agent-fabric/memory/fabric-coordinator/solution/subagent-tools-and-transcripts.md) — What a Claude Code custom agent file's tools line really does (empty = every tool; none is refused), and what a subagent's transcript and sidecar carry — read back live 2026-09-17
- [`.agent-fabric/memory/fabric-coordinator/solution/system-prompt-replacement-mechanics.md`](.agent-fabric/memory/fabric-coordinator/solution/system-prompt-replacement-mechanics.md) — What --system-prompt-file replaces and what the harness still injects (read back live 2026-09-17), and the identifier rule a translated prompt must keep

## workflow

- [`.agent-fabric/memory/fabric-coordinator/workflow/a-wrong-why-outlives-the-code.md`](.agent-fabric/memory/fabric-coordinator/workflow/a-wrong-why-outlives-the-code.md) — When deferring work, record the cost you measured — never a blocker you inferred from your own failed attempt
- [`.agent-fabric/memory/fabric-coordinator/workflow/adr-no-inline-attribution.md`](.agent-fabric/memory/fabric-coordinator/workflow/adr-no-inline-attribution.md) — No "(the owner, YYYY-MM-DD)" in an ADR body or DIGEST, and no date at all in §2–§8 (§1 may date an incident) — ADR-001 §5 rules 10–11, adr.py check refuses both
- [`.agent-fabric/memory/fabric-coordinator/workflow/blind-review-loop.md`](.agent-fabric/memory/fabric-coordinator/workflow/blind-review-loop.md) — How to review a fabric change — render a request with bin/fabric-review, dispatch code-review on fable with the brief verbatim, POST the brief, the report and the per-finding judgement on the PR, fix, then re-review the fix range with…
- [`.agent-fabric/memory/fabric-coordinator/workflow/check-exit-status-not-pipe.md`](.agent-fabric/memory/fabric-coordinator/workflow/check-exit-status-not-pipe.md) — Never `check | tail -1 && git commit`: the pipe's status is tail's, so a failed lint/static/suite still commits — run the check, capture rc=$?, commit only on 0
- [`.agent-fabric/memory/fabric-coordinator/workflow/cross-repo-lint-window.md`](.agent-fabric/memory/fabric-coordinator/workflow/cross-repo-lint-window.md) — A fabric push that changes what a project's index must list reddens that project's queue until its index PR merges — hold the push for a quiet queue until fabric-ref is live; and never chain a commit behind a piped test run
- [`.agent-fabric/memory/fabric-coordinator/workflow/distribute-after-merge.md`](.agent-fabric/memory/fabric-coordinator/workflow/distribute-after-merge.md) — After a fabric PR merges, distribute it to every account yourself — fabric-ctl all upgrade fabric, run before moving your own checkout — a broadcast alone is not distribution
- [`.agent-fabric/memory/fabric-coordinator/workflow/fleet-ops-via-control-plane.md`](.agent-fabric/memory/fabric-coordinator/workflow/fleet-ops-via-control-plane.md) — An operation on accounts (move Claude account, sync, verify, restart) goes through signed control-plane messages, never hostexec/sudo per login — build the action if it is missing
- [`.agent-fabric/memory/fabric-coordinator/workflow/guard-must-catch-the-shape-it-replaced.md`](.agent-fabric/memory/fabric-coordinator/workflow/guard-must-catch-the-shape-it-replaced.md) — A guard added alongside a fix is verified by planting the exact shape the fix removed — not the shape you had in mind when you wrote the pattern
- [`.agent-fabric/memory/fabric-coordinator/workflow/hook-probe-writes-binding.md`](.agent-fabric/memory/fabric-coordinator/workflow/hook-probe-writes-binding.md) — Running session-start.sh by hand as yourself rewrites your own binding's session id — the id the launcher resumes after a restart; probe with AGENT_FABRIC_STATE_DIR set to scratch
- [`.agent-fabric/memory/fabric-coordinator/workflow/house-i18n-standard.md`](.agent-fabric/memory/fabric-coordinator/workflow/house-i18n-standard.md) — Translated strings follow the house i18n standard — check a managed project for an existing convention before inventing a file format
- [`.agent-fabric/memory/fabric-coordinator/workflow/local-grep-is-ugrep.md`](.agent-fabric/memory/fabric-coordinator/workflow/local-grep-is-ugrep.md) — On develop-qzapp `grep` resolves to ugrep — tests/static.sh's sh-shebang check passed locally and failed in CI; verify a grep-based guard with /usr/bin/grep before trusting a local green
- [`.agent-fabric/memory/fabric-coordinator/workflow/pr-band-accumulate.md`](.agent-fabric/memory/fabric-coordinator/workflow/pr-band-accumulate.md) — One open PR per agent (gzapp's rule, with its exceptions) and 8–16 work commits to arm — the next piece of work is another commit, never a PR per topic; two one-commit PRs in a morning was the mistake
- [`.agent-fabric/memory/fabric-coordinator/workflow/prompt-change-readback.md`](.agent-fabric/memory/fabric-coordinator/workflow/prompt-change-readback.md) — After changing any role's charter, brief, prompt template or the team section: run `runtime/openrouter/launch --print` as a holder of that role (hostexec --as) before pushing — lint and tests did not check the rendered total until…
- [`.agent-fabric/memory/fabric-coordinator/workflow/redirecting-a-request-moves-its-credential.md`](.agent-fabric/memory/fabric-coordinator/workflow/redirecting-a-request-moves-its-credential.md) — When a fix changes WHERE a request goes, list every credential that travels with it first — clearing the destination alone can send a secret to a third party
- [`.agent-fabric/memory/fabric-coordinator/workflow/request-dies-with-its-session.md`](.agent-fabric/memory/fabric-coordinator/workflow/request-dies-with-its-session.md) — A GZCoord REQUEST that was acknowledged and deferred is lost when that session ends — the cursor has moved past it and no later session of the same login will ever see it
- [`.agent-fabric/memory/fabric-coordinator/workflow/review-p3-may-defer.md`](.agent-fabric/memory/fabric-coordinator/workflow/review-p3-may-defer.md) — P1/P2 review findings are fixed in the PR; a P3 may be carried to a later PR instead of another fix round
- [`.agent-fabric/memory/fabric-coordinator/workflow/sign-published-pages.md`](.agent-fabric/memory/fabric-coordinator/workflow/sign-published-pages.md) — Every page published for the owner carries a signature footer — the agent's host/login, the role held, the date, the revisions it rests on, who was consulted; the owner also likes reports as browser pages
- [`.agent-fabric/memory/fabric-coordinator/workflow/skills-no-prs-no-dates.md`](.agent-fabric/memory/fabric-coordinator/workflow/skills-no-prs-no-dates.md) — Writing or changing a SKILL.md: load the skill-creator skill first and follow it; never cite a PR number, an incident date or a project name inside a skill — the skill states the rule and the procedure, the docs and the commit carry the…
- [`.agent-fabric/memory/fabric-coordinator/workflow/smoke-container-before-ci.md`](.agent-fabric/memory/fabric-coordinator/workflow/smoke-container-before-ci.md) — Run a platform smoke job under podman on this host, as an unprivileged login, before pushing a CI change that adds a container job — the containers find host facts (a missing cmp, Debian's /etc/profile resetting PATH, dash as sh) that the…

## threads

- [`.agent-fabric/memory/fabric-coordinator/threads/assemble-hygiene-inconsistent.md`](.agent-fabric/memory/fabric-coordinator/threads/assemble-hygiene-inconsistent.md) — CLOSED 2026-09-20: assemble substitutes a banned term in place on both paths (new claim and carried text) since the 2026-09-16 decision; only non-English prose is still refused in a claim and reported in carried text — both make the run…
- [`.agent-fabric/memory/fabric-coordinator/threads/assemble-subheading-breaks-idempotence.md`](.agent-fabric/memory/fabric-coordinator/threads/assemble-subheading-breaks-idempotence.md) — FIXED 2026-09-25 (cac5a04): a claim body's own `## ` headings are demoted at render time and old split slices are absorbed; test_a_claim_body_s_own_headings_never_open_a_section
- [`.agent-fabric/memory/fabric-coordinator/threads/drain-report-last-run-wins.md`](.agent-fabric/memory/fabric-coordinator/threads/drain-report-last-run-wins.md) — FIXED (135b02b, ed5ca52): the drain report gathers every bundle of one drain and keeps each harvest; was — per-bundle runs overwrote last-drain-report.json
- [`.agent-fabric/memory/fabric-coordinator/threads/inbox-history-mode.md`](.agent-fabric/memory/fabric-coordinator/threads/inbox-history-mode.md) — To do: gzcoord inbox.mjs needs a history-listing mode (a seq range, addressed-to-me only, HELLO/GOODBYE filtered) — an agent planned ~400 --replay calls to read 3808..4200; replay already fetches 500 records per call
- [`.agent-fabric/memory/fabric-coordinator/threads/shared-android-toolchain-deferred.md`](.agent-fabric/memory/fabric-coordinator/threads/shared-android-toolchain-deferred.md) — Shared Android SDK / Gradle cache for Flutter logins on develop-qzapp — planned, deferred by the owner while flutter-dev-01 is the only user; revisit when a second Flutter login starts building
- [`.agent-fabric/memory/fabric-coordinator/threads/suite-scratch-leak.md`](.agent-fabric/memory/fabric-coordinator/threads/suite-scratch-leak.md) — tests/run.sh fails naming anything a run left under TMPDIR (since agent-fabric #26, 2026-09-20); node suites use tests/scratch.mjs, static.sh refuses inline mkdtempSync; never run the suite twice at once — the two share scratch and fail…

## recall

- [`identities/roles/fabric-coordinator/recall.md`](identities/roles/fabric-coordinator/recall.md) — How to ask the control plane about itself: status, routing, lint, migration records.

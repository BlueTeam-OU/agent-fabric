# ADR-019 — Work arrives as pull requests: one open PR per agent, 8–16 work commits to arm, the gate read before arming, no machine attribution, repository settings

**Date:** 2026-09-18
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** identities/prompt/team.md (the PR rules every session reads); runtime/github/pr-gate.sh, runtime/github/commit-class.sh, runtime/github/pr-review-status.sh; policies/ban_generated_by_attribution.sh and policies/githooks/commit-msg; .github/workflows/ci.yml; tools/fabric/github-repo-settings.sh and the GitHub-side settings of gzapi-org/agent-fabric
**Pillar:** P3

## 1. Context and Problem

Until 2026-09-18 the coordinator committed to agent-fabric's `main`
directly, and the note that recorded the repository's settings said so.
Every managed project already took its work as pull requests, gated by a
review and CI, and the fabric's own changes had begun to break those
projects' runs. A pull request is where a change becomes an artifact
others can check before it lands (ADR-000, P3: a conversation is not a
decision until it reaches an artifact).

Two failures shaped the rules around it. PRs were opened per topic — two
one-commit PRs from one session in one morning (2026-09-19) — so each
paid a full review and CI cycle and the owner's attention for a sliver of
work; and a PR's size was judged by eye. Separately, the harness injects
an instruction to add a `Co-authored-by:` trailer and a session URL, and
it re-arrives with every model change: two sessions, days apart, lost the
rule against it in two different shapes.

## 2. Decision

**Work arrives as pull requests.** Every change reaches `main` through a
pull request; on agent-fabric every change from #11 onward has been a
merged PR.

**One open pull request per agent**. While an
agent has a PR open, its next piece of work is another commit on it, if
the branch is still addable; otherwise it is built locally and waits for
the merge. Concerns are commit boundaries, not PR boundaries.

**A PR is armed by its work-commit count**: the
commits of work as opened, review fixes excluded. Eight to sixteen arm
once the gate is met; fewer ask the owner, who arms; more than sixteen is
split before the PR opens.

**The gate is read before arming.** `pr-gate.sh` gives each open PR one
verdict from its checks, its review, its threads and its merge state;
arming follows a `MERGEABLE` verdict and nothing else.

**No machine attribution, anywhere** — no `Co-authored-by:` or
`Claude-Session:` trailer, no session URL, no "Generated with" footer, in
a commit message or a PR description.

**The repository's GitHub settings are recorded here**, since they live
outside git, and `tools/fabric/github-repo-settings.sh` reapplies the
part it covers.

## 3. Alternatives Considered

- **Direct commits to `main` by the coordinator** (the earlier practice,
  §1).
  Rejected in practice: no review before landing, no CI before landing,
  and a fabric change reached every project's check unreviewed.
- **A PR per topic, or "small, reviewable pull requests"** (the
  coordinator's earlier charter wording). Rejected by the
  owner: each costs a review, a CI run and an arming; topics are commits.
- **No exceptions to one-open-PR.** Tried and withdrawn within a
  day: a finding on the queued PR itself and an urgent fix are
  real exceptions.
- **Counting all commits.** Rejected: review fixes would push a PR over
  the band for being reviewed; they are excluded by an `Answers:` trailer
  or, without one, by the subject's shape (`commit-class.sh`).
- **Trusting the harness settings alone for attribution.** Rejected: the
  setting reaches an account only through its last bootstrap (ADR-008),
  so the commit-time and CI guards stay.

## 4. Rationale

The band spends the owner's attention where it matters: a PR large enough
to be worth a review round is armed by the gate, a small one is the
owner's call, and an oversized one is caught before review. One PR per
agent makes a session's in-flight work one artifact to review and one
place to look. Reading the gate's verdict before arming — rather than
chaining a merge after a check — makes the arming depend on the verdict,
not on a pipe's exit status.

## 5. Binding Rules

1. Every change reaches a repository's `main` through a pull request;
   the author opens it, and it lands only through the gate (rule 5).
2. One open pull request per agent. While one is open — unarmed, armed
   or queued — the next work is another commit on it while the branch is
   addable. A branch stops being addable when the next piece depends on
   something merged, the branch is queued or merged, it touches a slow or
   flaky surface that would hold the rest hostage, the urgency differs, or
   the band's ceiling is reached. Two exceptions, each stated in the new
   PR's description: a finding on the queued PR itself (prefer dequeuing
   and fixing on the same head), and a fix that must land now (a
   user-visible or CI-blocking defect).
3. Work commits are counted by `runtime/github/commit-class.sh`: a merge
   is a merge; a commit with an `Answers: <labels>` trailer is a review
   fix; without one, a subject that names a review and says it answers one
   is a fix; a revert and the commit it reverts, both in the range, count
   in no column; everything else is work.
4. Eight to sixteen work commits: arm once the gate is met. Under eight:
   ask the owner, who arms. Over sixteen: split before the PR opens; a PR
   already open over sixteen is armed on its basis, and the count is
   advice for the next batch.
5. The gate is `runtime/github/pr-gate.sh`'s verdict for the PR, read
   before arming: `MERGEABLE` needs checks green, a review on the current
   head (`pr-review-status.sh`), no unresolved thread, no conflict, no
   draft and no unfolded supply. The verdict does not read the review's
   findings; the session also has no open P1 or P2 finding before it arms
   (`identities/prompt/team.md`). Arming is a separate command, run on a
   verdict read — never chained behind the gate's own run.
6. What arming is depends on the repository. agent-fabric's `main` is
   held by a ruleset (`tools/fabric/github-ruleset-main.json`): a pull
   request, the CI checks and signed commits are required, and deletion
   and force-pushes are refused. With auto-merge on, a PR there is armed
   with `gh pr merge --auto --merge`, which waits for green; every merge
   is made from the one GitHub account every session uses, and a PR that
   introduces a new direction is merged only on the owner's word (ADR-001
   §5 rule 2). A managed project with a merge queue is armed with its own
   `tools/gh/arm.sh`.
7. No commit message or PR description carries `Co-authored-by:` or
   `Claude-Session:` as a trailer, a "Generated with Claude Code" footer or
   a session URL: `policies/githooks/commit-msg` refuses the message,
   `policies/ban_generated_by_attribution.sh` checks every commit a branch
   adds and the PR description in CI and in `tests/run.sh`.
8. agent-fabric's GitHub settings are the table in §6. A change to them
   is a change to this record, and `tools/fabric/github-repo-settings.sh`
   is changed with it.

## 6. Consequences

- **agent-fabric on GitHub, as read with `gh api`:**

  | setting | value |
  |---|---|
  | visibility, default branch | public, `main` |
  | description | "Control plane for the agents working on sibling repositories: identities, roles, memory, model routing, messaging." |
  | features | issues, projects, wiki on; discussions off |
  | merge methods | merge commit (title `MERGE_MESSAGE`, message `PR_TITLE`), squash (`COMMIT_OR_PR_TITLE`, `COMMIT_MESSAGES`), rebase — all allowed |
  | auto-merge | on (it waits for the ruleset's required checks) |
  | delete branch on merge, suggest updating branches | off |
  | web commit sign-off | not required |
  | ruleset on `main` | `tools/fabric/github-ruleset-main.json`: deletion and force-push refused; a pull request (merge commits only, no approval count); the CI jobs `static`, `guards-and-suites` (8) and `platform-smoke` (2) required; signed commits required. No merge queue, no branch protection beside it |
  | Actions | enabled, all actions allowed, SHA pinning not required; default workflow permissions read, may not approve pull requests |
  | secrets, variables, environments, self-hosted runners | none |
  | code scanning | CodeQL default setup (actions, JavaScript/TypeScript, Python), weekly and on every PR |
  | secret scanning | on, with push protection, validity checks and non-provider patterns; AI detection off |
  | Dependabot security updates | off |
  | access | one collaborator, the owner; no teams, no webhooks |

  Everything the fabric's own CI runs is in the tree (`.github/workflows/ci.yml`,
  `tests/run.sh`, `policies/`); CodeQL's default setup and secret scanning
  are the GitHub-side exceptions, and `github-repo-settings.sh` sets
  neither. The check names a PR reports are per matrix leg —
  `guards-and-suites (3.12, 22)` and its siblings, `static`,
  `platform-smoke (…)` — so a required check, if one is ever wanted, names
  those.
- Nothing on GitHub enforces rules 1, 2, 4 or 5 on agent-fabric; they are
  practice, read to every session in `team.md`, and visible in the history.
- A managed project's CI checks this public repository out without a
  credential, at the commit its `fabric-ref` pins (ADR-011).

## 7. Future Evolution

- The note this record replaces said agent-fabric's commits go to `main`
  directly and gave the description ending "GZCoord" and a required-check
  context `ci / guards-and-suites`; the first no longer holds (§1), the
  second was changed on GitHub, the third is not a name GitHub reports.
  `github-repo-settings.sh` now writes the live description.
- The required checks are the CI job names GitHub reports, two of them
  truncated matrix names: a job renamed or a matrix argument changed in
  `.github/workflows/ci.yml` blocks every merge until the ruleset names
  it. One aggregate job required alone would remove that coupling.

## 8. Decision Status

Accepted and in force: the attribution ban, pull requests only, the
band, one open PR per agent. The settings note is now a stub pointing here.

## References

- `identities/prompt/team.md` (the band, one open PR, the gate's
  conditions), `CLAUDE.md` §"Git discipline".
- `runtime/github/pr-gate.sh`, `runtime/github/commit-class.sh`,
  `runtime/github/pr-review-status.sh`, and their tests.
- `policies/ban_generated_by_attribution.sh`, `policies/githooks/commit-msg`.
- `tools/fabric/github-repo-settings.sh`, `.github/workflows/ci.yml`.
- `.agent-fabric/memory/fabric-coordinator/workflow/pr-band-accumulate.md`,
  `.agent-fabric/memory/fabric-coordinator/workflow/check-exit-status-not-pipe.md`.
- ADR-000 (P3), ADR-001 (ratification by merge), ADR-008 (attribution in
  user settings), ADR-011 (fabric-ref), ADR-018 (the commit-time guards).

## Amendments

The body above reads current; each change's full note is in [history/ADR-019-amendments.md](history/ADR-019-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-04 | `main` is protected | §5 rule 6, §6: a ruleset requires a pull request, the CI checks and signed commits; auto-merge on, so arming waits for green |

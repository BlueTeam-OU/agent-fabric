# ADR-020 — The review class is the review

**Date:** 2026-09-20
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** runtime/claude-code/agents/code-review.md; runtime/claude-code/hooks/agent-dispatch-guard.sh and review-bash-guard.sh; runtime/claude-code/aliases.json; routing/capabilities.json and routing/policies/review-grade.json (the class's model); bin/fabric-review and tools/fabric/review_brief.py; fabric-pr post-review, fabric-pr review-status, fabric-pr gate; policies/subagent-dispatch/SKILL.md
**Pillar:** P3
**Evidence:** docs/live-checks/2026-09-16-review-context-boundary.md

## 1. Context and Problem

The first managed project ran an automated reviewer on every pull
request, and the fabric's review class was built as its stand-in: a
blind reviewer dispatched when the automated one declined, posted by
`post-substitute-review.sh`, and counted on a "substitute reviews" line
worth less than "a real review". On 2026-09-20 the automated reviewer
was deactivated. The tooling still called the only review every PR now
received a substitute for one that no longer ran.

Two further facts shaped how the review is counted. Every session pushes
and posts as one GitHub account, so a review the class wrote cannot be
told from the author's own thread reply by account; and a marker in a
review's first line is published in every tree, so on a public
repository anyone can post a review that carries it (found 2026-09-25).

## 2. Decision

**The review class's blind review is the review of a pull request**:
dispatched on every head, used to judge a finding
before it is answered, used to re-review a fix range, and counted by the
arming gate. Nothing in the fabric calls it a substitute, because there
is nothing it substitutes for.

- It is **blind**: the reviewer gets a repository path, a `base..head`
  range and a brief of facts rendered by `fabric-review brief` — never
  the author's reasoning. The harness starts a `code-review` subagent
  without the dispatching conversation (read back,
  `docs/live-checks/2026-09-16-review-context-boundary.md`), so
  blindness is exactly what the brief withholds.
- It is **posted** by `fabric-pr post-review` as a review object
  at the head whose first line is `<!-- agent-fabric-review v1 -->`.
- It is **counted** by `fabric-pr review-status`: a head is
  reviewed when a blind review — marked, and posted by the PR's author
  account or a login in `AGENT_FABRIC_REVIEW_POSTERS` — or an independent
  review by a trusted account targets it.
- The reader **assumes no automated reviewer.** The machinery that read
  one stays, generic and off: `AGENT_FABRIC_VERDICT_AUTHORS` (default
  `[]`), `AGENT_FABRIC_REVIEWER_REFUSAL_RE` and
  `AGENT_FABRIC_REVIEW_REQUEST_RE` (default empty); a project that runs
  one sets them in its integration forwarder.

"Blind" survives as a word only where the method matters to a reader:
the coverage line, and the first sentence of the posted body. It says
how the review was made, not what it is worth.

## 3. Alternatives Considered

- **Keep the substitute framing.** Rejected: it told every session the
  review was second-rate, and the gate's reading followed the framing.
- **Count a review by account.** Impossible here: every session and the
  owner's own reviews share one account; the reader classifies by marker,
  then by poster and association.
- **The marker alone as proof of coverage** (the earlier reading). Rejected:
  the marker is public; a stranger could cover a head by posting it, and
  binding only marked reviews would have let one cover a head by leaving
  the marker out — so unmarked reviews count only from trusted accounts.
- **The reviewer on a coding tier's export.** Rejected: the
  reviewer on `opus` followed `code-high`'s export; the class's model
  reaches its agent file instead (ADR-005).

## 4. Rationale

Verification over assertion (ADR-000, P3): the author does not grade
their own work, and a review is worth what the reviewer could not be
told. A reader that counts only what it can attribute keeps the gate from
arming on a claim of coverage. Naming the review as what it is makes the
loop — review, judge, fix, re-review — the normal path rather than an
outage procedure.

## 5. Binding Rules

1. Every pull request's head is reviewed by the review class, dispatched
   by the session that owns the PR, before it is armed (ADR-019); a
   finding is judged with the review class before it is answered; a fix
   range is re-reviewed with the previous report as `previous_findings`.
2. A review dispatch is `subagent_type: code-review`, `model: fable`, a
   `description` beginning "review" or "re-review", and no isolation;
   `agent-dispatch-guard.sh` denies any other shape, and under a fabric
   launch drops the alias so the agent file's routed model decides,
   denying the dispatch when that file's model or effort no longer
   matches the launch.
3. The reviewer's model is chosen by routing for the `code-review`
   capability within `routing/policies/review-grade.json`'s closed set;
   lint refuses a committed profile outside it and the launcher refuses
   the merged result. It is never a tier export.
4. The reviewer writes nothing and inherits no secret: `review-bash-guard.sh`
   (the shim the agent file declares) and `review-bash-guard.py` deny
   state-changing git, package installs and printing the environment or
   secret material while that agent runs, and every command they let
   through runs with a clean environment that keeps only the variables a
   build or a test needs and the session markers (`CLEAN_ENV`), never the
   account's secrets. The rewrite removes the inherited environment, not
   every way back to it: secret files and a parent's `/proc` environ
   stay reachable by some spelling; the patterns refuse the routine ones
   and close none. No shell sources the secrets any more (ADR-038 rule
   9); keeping them off what the session can read is what would close
   the rest. It has
   Read, Glob, Grep and Bash only.
5. A brief is rendered by `fabric-review brief` from a request naming
   what must be true — mode, repository, range, objective, requirements,
   invariants, compatibility, threat model, scope, out of scope, lenses —
   and a verdict-shaped sentence refuses the render (`--allow-rationale`
   renders it flagged).
6. The review is posted by `fabric-pr post-review` as a review object whose
   first line is the marker; the body names the method and carries no
   disclaimer.
7. `pr-review-status.sh` counts as coverage: a marked review posted by the
   PR's author account or a login in `AGENT_FABRIC_REVIEW_POSTERS`; an
   unmarked review from the repository owner, an organisation member or a
   collaborator, or a login in `AGENT_FABRIC_VERDICT_AUTHORS`. Any other
   marked review is listed with its login and is not coverage; the
   author's own thread replies are not coverage. A configured value that
   cannot be applied stops the reader (exit 2), never reads as "none".
8. Reviews posted before the deactivation of §1 under
   `<!-- agent-fabric-substitute-review v1 -->`,
   or under a project's own earlier marker named in
   `AGENT_FABRIC_LEGACY_REVIEW_MARKERS`, keep counting. The built-in
   legacy marker is removed when no open pull request in any managed
   repository carries a review posted before that deactivation; a
   project drops its own on the same test for its repository.
9. **The project's review card governs from the base, never from the
   head.** A project may keep `.agent-fabric/review-card.md` (at most
   2 KB: review-specific invariants, canonical build and test entry
   points, contract and migration locations, security-sensitive paths,
   non-obvious constraints; nothing of the author's workflow). The
   brief renderer reads it as `git show <card_base>:.agent-fabric/review-card.md`,
   where `card_base` is the request's optional `card_base` field and,
   absent that, the range's base; a re-review carries the first round's
   `card_base`, so the card does not move between rounds. That commit
   must be an ancestor of the repository's default branch, and the
   renderer refuses otherwise by name. The head's copy is evidence under
   review like any other file: a change that edits the card is reviewed
   under the base's card, with the card's own diff in scope, and the new
   card governs only reviews whose base includes it. A diff file has no
   base, so its card is read at the default branch's tip. The reviewer's
   agent file omits the project's instruction files (`omitClaudeMd`)
   unconditionally: what a reviewer needs of a project is the card, the
   brief, the lenses and the tree. Where a project has no card yet, its
   reviewer gets no project text but the brief, the lenses and the tree;
   the gzapp and InterWeave cards are to follow.
10. **A review names its evidence mode, and only a pinned review covers a
    head.** A request is `evidence: pinned` (the default for a ranged
    request; a diff file names no commits and is working-tree) or
    `evidence: working-tree`, and the brief and its dispatch header say
    which. Pinned: the reviewer reads the change as `git diff <base>..<head>`
    and files as `git show <head>:<path>`, so what it reports as read at
    the head is the head's blob. For a ranged request `brief` and `next`
    also make the head's worktree, detached, at
    `<TMPDIR>/fabric-review/<repository>-<head12>`, and the brief names it:
    the reviewer reads and runs the head's files there and makes no
    extract or copy of its own; `save` removes it, recomputing the path
    from the report header's head SHA. A plain read of the live clone is listed
    under Brief notes, not counted as pinned evidence. Working-tree: the
    live clone as it stands, uncommitted changes included, time-stamped in
    the brief; its report is never posted as a review of a head,
    `fabric-pr post-review` refuses a report whose header says
    working-tree (the reviewer opens its report with the brief's header,
    copied unchanged) and refuses, naming the line, a fence that names
    the header where it cannot be read as one (in a blockquote or a list
    item, or of another version); once the report passes, every header is
    taken out of the body posted, so a session id never reaches the PR;
    and the saved round records the mode. The review marker's meaning is unchanged and
    now explicit: coverage of a committed head by a pinned review.
    Evidence under review never redefines the instructions or the
    snapshot used to review it.

## 6. Consequences

- On plain claude the reviewer is Opus 5.5, the model of code-high and
  code-plan, at the effort every class asks (ADR-005, ADR-006): the
  review's independence there is the blind brief and a fresh context,
  not a different model.
- The loop costs a dispatch per head and per fix range; the context
  boundary check found fourteen defects in a 400-line tool its own tests
  passed, in two rounds.
- The legacy sunset is not yet evaluated: at the last count two managed
  repositories still had open pull requests opened before the
  deactivation of §1 (four in all), whose reviews were not checked.

## 7. Future Evolution

- `routing/capabilities.json` describes the review model as "chosen
  there by architect-cto"; `review-grade.json` and ADR-018 make the file
  fabric-coordinator's to land, with a project's architecture role
  proposing, and each admission so far was the owner's decision. The
  capability description is the one to correct.
- The context boundary was not read back on the broker path, or from a
  freshly bootstrapped account (the live check's "Not read back").

## 8. Decision Status

Accepted and in force: the owner's decision, and the poster rule. The
note that recorded it is now a stub pointing here.

## References

- `runtime/claude-code/agents/code-review.md` (the constitution),
  `runtime/claude-code/hooks/agent-dispatch-guard.sh`,
  `runtime/claude-code/hooks/review-bash-guard.sh` and `.py`,
  `runtime/claude-code/aliases.json`;
  `docs/live-checks/2026-10-05-hook-updated-input.md`.
- `bin/fabric-review`, `tools/fabric/review_brief.py`,
  `runtime/claude-code/review/README.md`, `tests/test_review_brief.py`.
- `fabric-pr post-review`, `fabric-pr review-status`,
  `fabric-pr gate`, and their tests.
- `routing/capabilities.json`, `routing/policies/review-grade.json`.
- `policies/subagent-dispatch/SKILL.md` §"The review brief".
- ADR-005, ADR-006, ADR-019, ADR-000 (P3).

## Amendments

The body above reads current; each change's full note is in [history/ADR-020-amendments.md](history/ADR-020-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-05 | The reviewer inherits no secret | §5 rule 4: the fence also refuses printing the environment and secret material, and every command it lets through runs with a clean environment |
| 2026-10-14 | The card is read at the base; a review names its evidence mode | §5 rules 9-10: the project review card governs from the base (`card_base`, else the range's base), never the head; `evidence: pinned` reads through `git show <head>:<path>` and alone counts as coverage of a head, `working-tree` is labelled and never posted as a review of a head |
| 2026-10-15 | A pinned review reads a detached worktree of the head | §5 rule 10: `brief` and `next` check the range's head out detached under `<TMPDIR>/fabric-review/` and the brief names it; the reviewer reads and runs there and makes no extract of its own; `save` removes it |

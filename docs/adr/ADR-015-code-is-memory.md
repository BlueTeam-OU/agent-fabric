# ADR-015 — Code is memory

**Date:** 2026-09-19
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** every repository the fabric coordinates, every role and every coding class; CLAUDE.md §"Working here" and runtime/claude-code/workspace/CLAUDE.md, through which it reaches a session; runtime/claude-code/agents/code-review.md §"Comments are engineering memory"; tests/test_review_brief.py (the reviewer's size cap)
**Pillar:** P2

## 1. Context and Problem

Every repository the fabric coordinates is maintained by fresh sessions:
the next engineer or agent to change a piece of code has the tree, its
tests and its documentation, and neither the conversation in which the
code was written nor any memory of why it was chosen. What such a
session cannot reconstruct from the code, it re-derives at cost, or it
"simplifies" away — an ordering, a defensive check, a workaround that
looked redundant and was required.

Two opposite habits make this worse. Comments that narrate what the code
visibly does spend context, widen the diff and go stale. Comments
trimmed to save tokens in the writing session drop exactly the reasoning
the next session needed. On 2026-09-19 the owner set one policy for every
repository the fabric coordinates.

## 2. Decision

**Code is memory for the session that comes after yours.** The goal is
not more comments and not narration; it is to preserve the engineering
reasoning a future maintainer — a person, or an agent session with none
of the context — cannot reconstruct from the code alone.

- Self-documenting code first: names, types, interfaces, functions,
  modules, tests and structure carry the *what*.
- A comment says *why*: a non-obvious design decision; an invariant later
  changes must keep; protocol semantics; a security, concurrency or
  distributed-system assumption; a compatibility, platform or
  interoperability constraint; an intentionally unusual choice; a
  performance trade-off; a workaround for an external system; a case
  where the simpler implementation would be wrong; a rejected alternative
  a maintainer would otherwise reintroduce; behaviour that must stay
  though a superficial refactoring would change it.
- The stronger executable form wins where one exists, in this order:
  code and naming → types and interfaces → assertions and invariants →
  tests → a local comment → module-level documentation → an ADR or
  architectural document. A comment complements an executable
  constraint, never replaces one.
- Comments are part of code correctness: a comment whose assumption a
  change made false is updated or removed in that change.
- The review class checks all of it.

It reaches every session launched under the workspace through
`CLAUDE.md` §"Working here": `bootstrap.sh` installs the workspace's
`projects/CLAUDE.md` (`runtime/claude-code/workspace/CLAUDE.md`), which
imports `agent-fabric/CLAUDE.md`, and a subagent receives the same
context. A managed project's own `CLAUDE.md` does not import it.

## 3. Alternatives Considered

- **A comment-density target, or "comment everything".** Rejected:
  density measures nothing; narration is noise that goes stale. The
  target is information per comment.
- **"The code should speak for itself" with no comments.** Rejected: the
  code says what it does, never why the obvious alternative was wrong;
  that is exactly what a fresh session reverses.
- **Terse comments to save context.** Rejected: a small saving in the
  writing session is a larger investigation in every session after.
- **Reasons in commit messages only.** Not sufficient: a commit message
  is not in front of the reader of the line; it complements a comment,
  test or record, and the stronger form still wins.

## 4. Rationale

An organization that is maintained by sessions without memory keeps its
memory in the artifact those sessions read first: the tree (ADR-000, P2).
Writing the *why* down is also a check on the writer: an agent that cannot
state why an unusual constraint exists should reconsider whether it
understands the change. Preferring an executable form turns a remembered
reason into one the build defends.

## 5. Binding Rules

1. A comment never restates what the code visibly does; such a comment is
   removed.
2. Reasoning that a competent future engineer or agent would, without it,
   likely misunderstand, simplify incorrectly or reverse is kept beside
   the code it explains — the test for every comment, kept or cut.
3. A useful comment is never trimmed to save tokens.
4. Where a type, an assertion or a test can carry an invariant, it does;
   a comment is the form of last resort below them, and a decision that
   spans modules goes in a decision record, not only in a comment.
5. Whoever changes code reads the comments around it and, in the same
   change, updates or removes any whose assumption is no longer true. A
   stale comment is a defect of the code.
6. Code that looks redundant, over-complicated, inefficient, strangely
   ordered, unusually defensive or contrary to convention on purpose says
   why beside it, unless a test, an invariant or a record already does.
7. The review class asks of every range, and grades as its constitution
   says (`runtime/claude-code/agents/code-review.md`): a comment that only
   narrates (P3); a non-obvious decision whose reason is nowhere — not in
   a comment, test, assertion or record (P3; P2 where a refactoring that
   removed it would remove required behaviour); an invariant left in
   prose that a type, assertion or test could enforce; a comment the range
   touches that is no longer true; a decision spanning modules that
   belongs in a record.
8. An agent that cannot state clearly why an unusual constraint or
   implementation exists reconsiders whether it understands the change
   before it makes it.

## 6. Consequences

- Review, and the author's own discipline, are the only enforcement: no
  lint measures a comment's worth, by design.
- The reviewer's constitution carries one more section, and its size cap
  (`SIZE_CAP` in `tests/test_review_brief.py`) was raised from 12 288 to
  13 000 bytes for it, paid on every review dispatch.
- A deferral's reason is a *why* too: it states the cost measured or the
  scope decided, never a blocker inferred from a failed attempt — the
  coordinator's own lesson of 2026-09-23, kept as a workflow slice.

## 7. Future Evolution

None stated. A lint for narration comments is not planned: what counts as
narration depends on what the code makes visible, which is a reviewer's
judgement.

## 8. Decision Status

Accepted: the owner's policy of 2026-09-19 (commit ca810dc), in force in
`CLAUDE.md` and the review class since that day. The policy note that
held it is now a stub pointing here.

## References

- `CLAUDE.md` §"Working here", `runtime/claude-code/workspace/CLAUDE.md`,
  `runtime/claude-code/bootstrap.sh` (the workspace file).
- `runtime/claude-code/agents/code-review.md` §"Comments are engineering
  memory"; `tests/test_review_brief.py`.
- `.agent-fabric/memory/fabric-coordinator/workflow/a-wrong-why-outlives-the-code.md`.
- ADR-000 (P2).

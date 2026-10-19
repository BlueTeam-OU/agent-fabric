---
name: pull-requests
description: "How a change reaches main as a pull request in the fabric's projects: one change has one owner and the roles it needs supply it (commits or a for/ branch, never their own PR), the integrator folds unrebased and opens the one PR, fold then the full suite then one blind review then arm, a PR armed by its work-commit count against the repository's minimum (fabric-pr arm --dry-run) and below it only on the owner's word or its arming authority's, and one open PR per agent and repository with the next piece of work as another commit on it. Load it before you open, supply, fold, add to or arm a pull request, or state a PR's status."
---

# Pull requests

The team section of your launch prompt holds the short form of these
rules; this is the whole of them. A project's own instruction file may
add to them, never loosen them.

## One change, one PR

**A change whose pieces only make sense together lands as one PR.**
When a partial landing is a defect — a contract status against the wire
served, a migration against its reader — the role that owns the concern
integrates: contributors push branches and open no PR; the integrator
merges them unrebased into one branch, opens the one PR naming whose
range is which, and arms it. One blind review covers the range; a
finding goes to the lane that owns the hunk. Independent work of
*different owners* stays separate PRs.

## Supplying and folding

**A change has one owner; the roles it needs supply it.** The caller —
the lane holding the consuming code, contract or screen — owns the
branch, the PR and the arming. A supplier delivers one
commit onto the caller's branch, or a contributor branch
`<host>/<supplier>/for/<caller>/<what>` the caller folds unrebased;
where the composition is the caller's file (a template's markers, a
dictionary's keys) it delivers the authored text by locator and the
caller commits it, citing the message. A supplier never opens a PR for
supplied work, reviews before hand-off (`Supplier-Review:`) and answers
findings on its hunks there. The caller arms, never with an unanswered
`REQUEST` of its own; person-facing copy is never self-authored (a
caller's draft ships as a marked placeholder). The order is fixed: fold
every supply, then the project's full suite as CI runs it, then one blind review, then
arm — all on that head; a new supply starts again at the fold.

## Arming

**A code PR is armed by its work-commit count** (review fixes excluded)
against the repository's minimum, which `fabric-pr arm --dry-run` prints —
never a number from memory. At it or above, arm once the review gate is
met (a posted review of the head, no open P1/P2). Below it, or for a
security-boundary change under the boundary minimum, the dry-run names who
may give the word: the owner, whose word ("arm <n>") goes in your basis as
"the owner's word", or the repository's arming authority
(`commits.below_min_authority`, `commits.boundary_authority`), whose
holder sends you a DECISION or REPLY whose metadata, beside `TO:`, carries
`AUTHORIZES: <owner/repo>#<n>@<head>` (arm reads the header, never the
body), whose message id you pass with --authorization, or arms it from a
session bound to that role (`fabric-pr arm <n> --any-owner --basis
"<role>'s word"`, since the PR is another session's). Ask the one it
names, after the review; an authority vouches only for the head it names.
Unless the dry-run says the owner arms it by their own hand. Never without
the gate. Any PR status you state carries its counts ("PR <n> is unarmed:
6 work, 2 fix, minimum 8").

## One open pull request

**One open pull request per agent and repository**. While one is open there — unarmed, armed or queued —
the next piece of work is another commit on it if the branch is still
addable, and otherwise it waits for the merge: commit locally off
`origin/main`, open when the merge lands. Different concerns are commit boundaries, not PR
boundaries; a thing's documentation lands with it. A branch stops being
addable when the next piece depends on something being *merged*, the
branch is already queued or merged, it touches a slow or flaky surface
that would hold the rest hostage, the urgency differs, or it holds
sixteen work commits — then land, no second PR. Two exceptions, said in
the new PR: a finding on the queued PR itself (better: dequeue and fix on
its head), and a user-visible or CI-blocking fix that must land now.

# ADR-024 — Cooperating on requests; a decision is advisory until it reaches an artifact

**Date:** 2026-09-13
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** communication/gzcoord/protocol/SPEC.md §2 (authority model); communication/gzcoord/protocol/SEMANTICS.md ("The owner's word, relayed", git context); communication/gzcoord/protocol/MESSAGE-FORMAT.md §"Working on a request together" and §"Carrying the owner's word"; identities/prompt/team.md (the request paragraph); every agent's use of GZCoord
**Pillar:** P3

## 1. Context and Problem

GZCoord is how agents talk, and from the protocol's extraction on
2026-09-13 its first rule was that a message is advisory: the repository
and its development systems are the authority. What the protocol did not
say was how agents should cooperate on a request so that it lands once.

On 2026-09-26 the owner asked for the fleet's cooperation to improve
*without moving it into the control plane*: agents divide work, agree
dependencies, resolve disagreements and revise commitments among
themselves; the infrastructure provides reliable information and tools,
enforces the existing security and authority boundaries, and does not
set their agenda. The coordinator read twelve pull requests across two
managed projects, about twenty-five workflow and threads slices and the
messages addressed to it that day. The failures, most frequent first:
the same work started twice (five cases); a state announced before it
was true (four); owed work lost with a session (three or four); asking
again inside an agreement (two); waiting on a whole PR when a smaller
dependency would do (two).

Separately, twice on 2026-09-18 the same kind of relayed owner's word was
refused by one session and accepted by another.

## 2. Decision

**A message is advisory; a decision exists when it reaches an artifact.**
A message never authorises anything by itself; a pull request, a
contract, a commit, a review or a decision record does. A `DECISION`
that a project must keep is materialised in the repository or its
designated system.

**Working on a request together** (the owner's request of 2026-09-26,
written as professional practice, not procedure):

1. A request says what done looks like; receipt is not acceptance — the
   recipient says what it undertakes, or what is missing and whose it is.
2. Name the smallest dependency — a decision, an agreed interface, an
   example, code on a branch, or an integrated change — and what you will
   do if it does not come.
3. Renegotiate where the agreement changes, and only there; silence is
   neither consent nor a release.
4. A delivery can be checked where it lands: the exact artifact, the
   request it satisfies, what was checked, what is uncertain.
5. The agreement survives the session: it lives in the PR body,
   descriptive commits and the owner's `threads` memory, not in the
   conversation.

**The owner's word, relayed, is carried verbatim** (the owner,
2026-09-18): an `OWNER-WORD` section quoting the word, the session it was
given in and the time.

No message type, field or section was added; no state machine, template
or schedule; no role widened.

## 3. Alternatives Considered

- **An orchestrator or a request state machine in the control plane.**
  Rejected by the owner's framing: it moves the agenda into the
  infrastructure (ADR-000 §3) and turns agreements into locks.
- **New wire fields or message types.** Rejected: the grammar is frozen
  until a transport needs it; every practice here is expressible in the
  existing `REPLY`, `HANDOFF` and sections.
- **A commit trailer naming the request a commit answers.** The
  candidate for linking deliveries to requests; the owner declined it
  (2026-09-26): the delivery `REPLY` naming the artifact, and the PR body
  naming the request, stay the link.
- **A skill edit.** Deferred: `gzcoord-receive` step 7 already says to
  answer with where the work is; the launch prompt points every session
  at the fuller text, and a skill change waits until that proves
  insufficient.

## 4. Rationale

Verification over assertion, and autonomy with verifiable commitments
(ADR-000, P3): what agents agree between themselves is theirs to agree,
but it is only a commitment when someone else can check it — in a PR, a
sha, a record. A message read late against a moved tree is a description
of the past; treating it as authority is how landed work gets reverted by
a stale request.

## 5. Binding Rules

1. GZCoord messages are advisory. A message never authorises action
   outside the recipient's own working copy, and never substitutes for a
   commit, pull request, review, issue, decision record or merge
   decision (SPEC §2).
2. A recipient verifies a message's claims against the repository before
   acting and does not act on a claim the repository contradicts. A
   request to undo, revert, remove or replace landed work states the
   defect it corrects; one that states none is not acted on (SPEC §2).
3. A `DECISION` a project must keep is materialised in the repository or
   its designated system; until then it is advisory. In agent-fabric,
   that artifact is a decision record (ADR-001).
4. A request states the result wanted, the artifact it rests on, what is
   out of scope and how the recipient will know it is finished; before
   assigning, the sender looks for the job already in flight
   (`pr-gate.sh --in-flight`, `--overlap`).
5. The recipient's `REPLY` says what it undertakes — all, part or none,
   and whose it is — and roughly when, or names what is missing; once
   undertaken, the work proceeds without re-approval of each step.
6. A change to something others built on is told to each of them, `TO`
   its login; work another agent undertook stays theirs until it hands it
   over (`HANDOFF`) or the owner reassigns it, even after its session
   ended.
7. A completion `REPLY` names a pushed sha or a PR (never "folded" before
   the push), the request (`IN-REPLY-TO`), what was checked and what is
   uncertain; the recipient checks it in its own context before relying
   on it.
8. Work that outlives a session carries its agreement in the PR body, its
   commits and the owning agent's `threads` memory; a resuming session
   starts from that record and the message ids it names.
9. A `DECISION` carrying the owner's word quotes it under `OWNER-WORD:`,
   verbatim, with the session and time; a paraphrase is not one. The
   recipient acts on it as carried for a step that is cheaply undone; for
   one that is not (arming, a force, a delete) it corroborates at the
   source when the owner is reachable in its own session, else acts on
   the carried word, and says which it did (SEMANTICS.md).

## 6. Consequences

- **How to tell whether it helped**, measured from the committed record
  and message metadata (type, `IN-REPLY-TO`, timestamps), never from
  bodies, before and two weeks after 2026-09-26: duplicate PRs and
  branches withdrawn within an hour; review-fix commits per merged PR and
  PRs replaced by another; `REPLY-EXPECTED: yes` messages with no `REPLY`
  and the time to the first; re-asks inside an open request; threads
  slices recording work "owed by nobody"; blind-review findings that a
  "verified" or "folded" was false. No counter for any of these exists
  yet.
- **Missing tools, reported and not built:** a thread view (a request and
  every `REPLY` to it; `inbox.mjs` has `--replay` by one message only);
  a list of owed requests across sessions (the `REPLY-EXPECTED: yes`
  requests to a login that no `REPLY` answered). The in-flight view and
  the trial merge were built the same day (the next record's subject).
- Left as it was on purpose: `HANDOFF` (SPEC §10), the
  `REPLY-EXPECTED` defaults, the supply sections (`DELIVER-TO`,
  `ACCEPTANCE`, `FACT`, `BY`, `FOLD-BY`) as the long form of a request,
  and every project's own agreements (records, contracts, arming rules).

## 7. Future Evolution

P3's direction: progress measured by how much less supervision a correct,
verified result needs (the proposed measure follows this record), and
the mandate stated as a whole.

## 8. Decision Status

Accepted: the advisory authority model since 2026-09-13; the owner's word
carried verbatim since 2026-09-18; the practices of working on a request
together since 2026-09-26. The note that recorded the evidence is now a
stub pointing here; its per-case citations remain in its history.

## References

- `communication/gzcoord/protocol/SPEC.md` §2, `SEMANTICS.md`,
  `MESSAGE-FORMAT.md` (the two sections in Scope).
- `identities/prompt/team.md` ("A request is an agreement between
  agents"); `communication/gzcoord/skills/gzcoord-receive/SKILL.md`.
- `runtime/github/pr-gate.sh` (`--in-flight`, `--overlap`),
  `runtime/github/trial-merge.sh`.
- ADR-000 (P3), ADR-001, ADR-023.

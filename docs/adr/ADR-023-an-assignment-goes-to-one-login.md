# ADR-023 — An assignment goes to one login

**Date:** 2026-09-19
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** communication/gzcoord/protocol/SPEC.md §13 and §18; communication/gzcoord/protocol/MESSAGE-FORMAT.md §"Direct versus role addressing"; communication/gzcoord/protocol/examples/; the validator in communication/gzcoord/scripts/gzmsg.mjs and communication/gzcoord/scripts/send.mjs; communication/gzcoord/skills/gzcoord-send and gzcoord-receive
**Pillar:** P3

## 1. Context and Problem

GZCoord lets a message be addressed to a login (`TO`), to whoever holds a
role (`TO-ROLE`), or to everyone. The runtime delivers a role address to
every holder (SPEC §13, option 1), and the spec forbade a runtime from
inventing an ownership rule between them — but said nothing to stop a
sender from putting it in that position.

On 2026-09-19 `backend-dev` had two holders on one host. An
`OBSERVATION` carrying a `REQUEST:` section, addressed `TO-ROLE:
backend-dev`, asked for a change to one section of one file. Both holders
did it, hours apart, as two pull requests on the same hunk: a
merge-queue run spent on a duplicate and a conflict for whichever landed
second. Neither `REPLY` named the other's PR; neither had seen it. The
protocol's own examples offered exactly that shape to copy. The owner:
"an assignment of a job must not be sent to a role."

## 2. Decision

**An assignment is addressed `TO` one login, never `TO-ROLE`** (the
owner, 2026-09-19). An assignment is a `REQUEST`, or any message
carrying a `REQUEST:`, `ACCEPTANCE:` or `DELIVER-TO:` section — a
finding to fix, a supply, a decision to record. `TO-ROLE` stays for what
is not an assignment: an `INFO` or a `DECISION` every holder applies, a
`QUESTION` to whoever holds the role. SPEC §13 states it as a MUST on
the sender and a MUST-reject on the validator; `send.mjs` refuses such a
message before it leaves.

A sender that does not know which holder chooses by a fixed order and
says in the body which rule chose. An assignment that reaches a role
anyway — a sender on an older text — is claimed by the first `REPLY`.

## 3. Alternatives Considered

- **Let the runtime pick one holder.** Rejected: SPEC §13 already
  forbids a runtime inventing an ownership rule; which holder is right is
  the sender's knowledge, not the relay's.
- **Keep role addressing and rely on the receivers to coordinate.**
  Insufficient alone: neither holder saw the other until both had acted.
  It stays as the fallback for an old sender (rule 5), not the rule.
- **A new field or protocol version.** Rejected: the grammar is frozen
  until a transport exercises it; a tightened MUST on an existing field
  retires a shape without adding one — every message valid under the new
  text was valid under the old.

## 4. Rationale

A commitment needs a party (ADR-000, P3): a job addressed to a role is
addressed to no one in particular and is done by everyone or no one. A
wrong choice of login costs one `REPLY` ("not mine — it is `<login>`'s");
a role address costs the work twice. Refusing the shape at the sender,
with the field named, is cheaper than any convention a receiver must
remember.

## 5. Binding Rules

1. A `REQUEST`, and any message carrying a `REQUEST:`, `ACCEPTANCE:` or
   `DELIVER-TO:` section, is addressed with `TO` naming one login.
2. A conforming validator rejects a `REQUEST` addressed `TO-ROLE` and any
   `TO-ROLE` message carrying one of those sections, naming the field at
   fault (SPEC §13, §18); `gzmsg.mjs` does, and `send.mjs` validates as
   the last step before posting, so such a message is not sent.
3. `TO-ROLE` is used only for what every holder applies or only the role
   decides: an `INFO`, a `DECISION`, a `QUESTION`.
4. A sender that does not know which holder chooses, in order: the holder
   whose open branch or pull request already touches the path
   (`pr-gate.sh --all`, `pr-sessions.sh --all`); else a holder with a
   session running now (`fabric-ctl all presence`); else the
   lowest-numbered login of the role — and says in the body which rule
   chose.
5. A holder that receives an assignment addressed to its role first
   checks for a sibling's `REPLY` to that `MESSAGE-ID` or an open PR on the
   path by another login of the role; if one exists it stands down with
   no message and no branch; otherwise its `REPLY` naming the branch is
   the claim, sent before the work. Two who acted before seeing each other
   close the later-opened PR, naming the earlier.
6. The protocol's examples of an assignment name a login.

## 6. Consequences

- The runtime still delivers `TO-ROLE` to every holder; §13's options
  stand for the messages that may still use it.
- Before posting a `TO` or `TO-ROLE` message, `send.mjs` asks the
  control plane whether the addressee has a running session and, if not,
  says so and exits 4 unless `--force`; a `TO-ROLE` with no running
  holder reaches nobody now.
- The rule binds a role with one holder as much as one with two: the
  coordinator's own `REQUEST` of the same morning to a single-holder role
  was the same shape, and would now be refused.

## 7. Future Evolution

None stated. `pr-gate.sh --in-flight` now also lists pushed branches
with no PR, which rule 4's first step can read.

## 8. Decision Status

Accepted: the owner's word of 2026-09-19, in SPEC §13, the validator and
both skills since that day. The note that recorded the change is now a
stub pointing here.

## References

- `communication/gzcoord/protocol/SPEC.md` §13, §18;
  `communication/gzcoord/protocol/MESSAGE-FORMAT.md` §"Direct versus role
  addressing"; `communication/gzcoord/protocol/examples/observation.txt`,
  `observation-diagnosis.txt`.
- `communication/gzcoord/scripts/gzmsg.mjs` (validate), `send.mjs`;
  `communication/gzcoord/tests/protocol.test.mjs`;
  `communication/gzcoord/i18n/en-US.json` (`validate.request-to-role`,
  `validate.section-to-role`).
- `communication/gzcoord/skills/gzcoord-send/SKILL.md`,
  `communication/gzcoord/skills/gzcoord-receive/SKILL.md` (step 6).
- ADR-000 (P3).

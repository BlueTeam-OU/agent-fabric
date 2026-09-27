# ADR-030 — Presence replaces HELLO and GOODBYE

**Date:** 2026-09-25
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #53 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the control agent's `presence` op (runtime/control/ops.mjs, runtime/control/presence.mjs); `fabric-ctl <login|all> presence`; the sender's check in communication/gzcoord/scripts/send.mjs; the inbox's handling of HELLO and GOODBYE (communication/gzcoord/scripts/inbox.mjs); what runtime/openrouter/launch and bin/fabric-role no longer send; communication/gzcoord/skills/gzcoord-send and gzcoord-receive
**Pillar:** P5
**Evidence:** docs/live-checks/2026-09-16-goodbye-from-the-launcher.md

## 1. Context and Problem

Until 2026-09-25 an agent was "online" when its `HELLO` was the last word
on the channel: the launcher sent one before each session and, from
2026-09-16, a `GOODBYE` after it — the launcher ran the session as a
child precisely so it could send the `GOODBYE` however the session ended.

On 2026-09-25 the host crashed and sixteen sessions ended with no
`GOODBYE`; every one of them still read as present. The same day a launch
cancelled at the resume picker sent a `HELLO`/`GOODBYE` pair five
seconds apart that another agent had to ask about, and the announcements
were most of what every watch delivered. An announcement is a claim a
session makes about itself, and the claims that matter most — "I am
gone" after a crash, "I never started" after a failed launch — are the
ones a session cannot make.

## 2. Decision

**Presence is asked of the control plane, never announced.** Each
account's control agent answers a `presence` request from its own
process table and binding: whether a `claude` session is running, how
many, since when, the role and project, and whether it is planning. The
launcher sends no `HELLO` and no `GOODBYE`; a role change sends nothing;
the inbox acknowledges an announcement from an older sender and never
delivers it. GZCOORD/1 deprecates both types without removing them.

- **Anyone asks it.** `presence` is the one public op of the control
  plane: any placed account may run `fabric-ctl <login|all> presence`.
- **The sender asks it.** Before a `TO` or `TO-ROLE` message leaves,
  `send.mjs` asks whether the addressee has a session; the sender decides
  what to do about the answer.
- **A request dies with its session.** A request sent to a session that
  then ended is not read by the next one; the sender checks presence and
  re-sends, with what changed, when a session is running.

## 3. Alternatives Considered

- **Keep the announcements, fix the gaps** — a `GOODBYE` from a
  `SessionEnd` hook, a heartbeat. Rejected: a hook fires on the exit paths
  the harness chooses (not a crash, a `kill`, a double Ctrl-C); a
  heartbeat is still a claim, and a stale one reads as present until a
  timeout guesses otherwise.
- **The relay's own view** (who is polling). Rejected: an inbox watch
  and a session are not the same thing, and the relay verifies no
  sender.
- **Remove HELLO and GOODBYE from the protocol (GZCOORD/2).** Rejected:
  no message changes meaning, and every sender still on an older text
  would stop parsing. Deprecation inside /1 retires the practice and
  keeps the grammar.

## 4. Rationale

The process table is the one source authoritative about whether a
session runs, and it is read by the account itself, whether or not a
session exists (ADR-029). A crash or a launch that never reached the
harness is never "present". Moving the question to the sender's side
turns "is anyone there?" from something every watch printed all day into
something asked once, when it matters.

## 5. Binding Rules

1. The control agent's `presence` answers from `pgrep -u <uid> -x
   claude` (not its own process) and `/proc`: `online`, `sessions`,
   `since` (the earliest start), `role` (derived as the inbox's delivery
   derives it, so a `TO-ROLE` the relay would deliver is never refused),
   `project` from the binding, and `planning` (the account's inbox is held,
   ADR-022) — a boolean, nothing more. A process table that cannot be read
   is `status: failed`, which every reader treats as unknown, never as
   offline.
2. `presence` is the only public op (`ops.mjs` `PUBLIC_OPS`, ADR-029 §5
   rule 4); every other op stays the operator's.
3. Before posting a `TO` or `TO-ROLE` message, `send.mjs` asks presence.
   An addressee with no session, a control agent that did not answer or
   could not tell, an address no host places, or a presence request that
   failed is named, nothing is sent, and it exits 4 — unless `--force`,
   which sends and says so. A relay that refuses the token skips the
   check with a line saying so, and the post reports the refusal. A
   `TO-ROLE` passes when any holder is running. A broadcast is not
   checked. A dry run asks nothing.
4. An addressee that is planning is said and still sent to — a note,
   never a refusal; for a `TO-ROLE`, only when every running holder plans
   and no account was silent.
5. The launcher sends no `HELLO` before a session and no `GOODBYE` after
   it; `fabric-role bind` and `unbind` send nothing. The session stays the
   launcher's child, which is what lets an upgrade or an account move
   bring it back (ADR-009).
6. The inbox acknowledges a `HELLO` or `GOODBYE` and never delivers or
   lists it; a replay by seq still shows one.
7. In GZCOORD/1, `HELLO` and `GOODBYE` are deprecated: an instance SHOULD
   NOT send them, presence is the deployment's to answer from an
   authoritative source, a receiver MUST NOT rely on either arriving, and
   a conforming parser still accepts both (SPEC §5).
8. A request whose addressee's session ended before acting on it is
   re-sent when presence shows a session running, saying what changed —
   never assumed to carry over.

## 6. Consequences

- A message to a login with no session waits in the relay until one
  starts; the sender now knows that before posting, and `--force` is the
  deliberate choice to let it wait.
- A send costs a presence round-trip, up to about six seconds when an
  account is silent (`PRESENCE_WAIT_MS`).
- Presence is only as available as the control plane: with the relay or
  the control agents down, a send says "unknown" and refuses without
  `--force`.
- The watches are quieter: on 2026-09-25 the announcements were most of
  what every watch printed.

## 7. Future Evolution

None stated. Removing the two types from the grammar would be a
GZCOORD/2 question, and nothing asks for it while a conforming parser
accepts them at no cost.

## 8. Decision Status

Accepted since 2026-09-25: the launcher, `fabric-role`, the inbox,
`send.mjs` and SPEC §5 carry it.

## References

- `runtime/control/ops.mjs` (`presence`, `PUBLIC_OPS`),
  `runtime/control/presence.mjs` (`askPresence`, `checkAddressees`),
  `runtime/control/ctl.mjs`, `runtime/control/tests/presence.test.mjs`.
- `communication/gzcoord/scripts/send.mjs`,
  `communication/gzcoord/scripts/inbox.mjs` (`ANNOUNCEMENT_TYPES`),
  `communication/gzcoord/tests/protocol.test.mjs`.
- `communication/gzcoord/protocol/SPEC.md` §5, §18.
- `runtime/openrouter/launch` (the session as a child), `tools/fabric/role.py`.
- `communication/gzcoord/skills/gzcoord-send/SKILL.md` §3–4,
  `communication/gzcoord/skills/gzcoord-receive/SKILL.md`.
- ADR-009 (the restart marker), ADR-022 (planning), ADR-023 (the
  holder-choice rule that reads presence), ADR-029 (the control agent).
- The live check in Evidence: the `GOODBYE` from the launcher, measured
  on 2026-09-16 and retired by this record.

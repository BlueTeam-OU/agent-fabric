# ADR-059 — Third-party personal data stays out of the Max plan

**Date:** 2026-10-16
**Status:** Accepted
**Ratified:** owner, 2026-10-16, in the coordinator's session, choosing "the opinion's (b)" on PR #278
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** what personal data of anyone other than Blueteam's own people may reach the Claude Max plan the fleet runs on; what the blueteam.ee privacy notice says of it. Not the OpenAI business account, which has a processing agreement (the opinion's §4)
**Pillar:** P3

## 1. Context and Problem

legal-expert-ee-eu's opinion on the blueteam.ee privacy notice
(`docs/legal/2026-10-15-privacy-notice-blueteam-ee.md`) found that the
Claude Max plan the fleet runs on is a consumer plan: it comes with no
processing agreement. Personal data that Blueteam processes for a
client may go only to a sub-processor the client has authorised in
writing and that is bound as the processor is, and a consumer plan
cannot be that sub-processor. The opinion put three options to the
owner: (a) run client work that touches personal data on a plan with a
processing agreement, (b) keep Max and keep all third-party personal
data out of it, (c) accept the risk, which it judged not lawful for
data processed for a client. It advised (a) for client systems and (b)
for everything else. The notice could not be adopted until this was
decided, because what it says about AI tools depends on it.

## 2. Decision

The fleet keeps the Max plan, and no personal data of a third party
(clients, their people, visitors of Blueteam's sites) goes into it:
cleaned logs only, no client repository with real commit history, no
production access. This is the opinion's (b) as it was worded. It
governs the Max plan only: an AI tool with a processing agreement (the
OpenAI business account) is outside it, and client personal data goes
there only as the opinion's (a) describes, under a later record.

## 3. Alternatives Considered

- **(a) A plan with a processing agreement for client work.** The
  opinion's advice for client systems. Not taken now: it means a second
  plan and moving client work onto it. A later record can adopt it, and
  this one then narrows to what stays on Max.
- **(c) Accept the risk.** Refused: the opinion judged it not lawful for
  data processed for a client.

## 4. Rationale

(b) keeps the fleet on the plan it runs on today and makes the notice
true by practice rather than by contract: data that never reaches the
tool needs no sub-processor clause. Its cost is discipline: every role
that touches a client's system keeps that system's personal data out.

## 5. Binding Rules

1. No personal data of a third party (a client, a client's people, a
   visitor of a Blueteam site) is given to the Max plan: not in a
   prompt, a file, a log, a repository or a tool's access.
2. Work on a client's system done on the Max plan uses cleaned data:
   logs with personal data removed, repositories without real commit
   history, no access to production data.
3. The blueteam.ee privacy notice describes the Max plan as receiving no
   third-party personal data, and is true only while rules 1 and 2 are
   kept; a change of practice changes the notice in the same step.
4. Adopting a plan with a processing agreement for some work is a new
   record that names the work and the plan.

## 6. Consequences

- The redraft of the notice
  (`docs/legal/2026-10-15-privacy-notice-blueteam-ee-draft.md`) is
  written on this decision; its bracketed facts are still the owner's.
- Client work that needs real personal data waits for a record under
  rule 4.
- The opinion's other points (client contracts authorising
  sub-processors, processing agreements with the named providers) stay
  open, for the owner.

## 7. Future Evolution

Reopened when client work needs real personal data, or when a plan with
a processing agreement is adopted (rule 4).

## 8. Decision Status

Accepted; the rules bind now. Nothing in the fabric's code
enforces them: they are practice, kept by every role.

## References

- `docs/legal/2026-10-15-privacy-notice-blueteam-ee.md` (the opinion,
  §6 point 1), `docs/legal/README.md`.

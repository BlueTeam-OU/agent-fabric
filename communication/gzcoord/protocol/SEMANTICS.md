# Semantics and Non-Semantics

This document exists to prevent GZCoord from slowly becoming a second project-management system.

## What a message means

`OBSERVATION`
: "I noticed this and think it may matter."

`QUESTION`
: "I need information or clarification."

`REQUEST`
: "I am asking you to do something."

`REVIEW`
: "Please examine this before the authoritative workflow proceeds."

`DECISION`
: "I am communicating a decision from my role/context. Record it where project policy requires."

`HANDOFF`
: "I am transferring context/responsibility by agreement."

## What a message does not mean

None of these messages automatically:

- creates a GitHub issue;
- changes an issue state;
- owns a branch;
- reserves a file;
- reserves a finding, task or fix for the sender;
- moves an agent out of the working copy it started in;
- grants access to another agent's checkout, branch or pull request;
- blocks a merge;
- approves a pull request;
- records an ADR;
- changes repository permissions;
- resolves a conflict;
- establishes durable organizational truth.

If such an effect is required, use the authoritative tool explicitly.

## When a reply is expected

Every message a transport carries has a cost — over a human relay, a person's. A thread therefore ends in silence, not in a closing message, and **an acknowledgement is terminal**: nobody acknowledges an acknowledgement. Completion is announced by the pull request; a piece someone asked for and is waiting on is also answered, once, by a `REPLY` that names it (MESSAGE-FORMAT.md, "Working on a request together").

By default:

- `QUESTION`, `REQUEST`, `REVIEW`, `HANDOFF` — a reply is expected: an answer, an acknowledgement by reference, a decline, an acceptance.
- `OBSERVATION` — a reply is expected only if the recipient acts on it, and then only to say where (MESSAGE-FORMAT.md, "Acknowledging by reference"). Its purpose is to prevent duplicate work, not to say thanks.
- `INFO`, `DECISION`, `REPLY` — no reply is expected.

`HELLO` and `GOODBYE` are retired (SPEC.md §8): nobody sends them, and a parser rejects either. Whether an instance is running is presence, which the deployment answers (SPEC.md §5).

`REPLY-EXPECTED: yes | no` (SPEC.md §7.4) overrides the default for one message. Neither the default nor the override obliges anyone: "expected" describes what the sender is waiting for, and "no" tells the carrier not to come back for one.

## The owner's word, relayed

A `DECISION` carrying an `OWNER-WORD` section (MESSAGE-FORMAT.md,
"Carrying the owner's word") is still a message: it authorises nothing
by itself. What it does is fix the recipient's behaviour, so that it is
not a per-session judgement:

- for a step that is cheaply undone — a rewording, a branch, a reply —
  act on the word as carried;
- for a step that is not — arming a merge, a force, a delete —
  corroborate at the source when the owner is reachable in your own
  session, and act on the carried word when they are not; either way,
  say which you did.

The gate that removes most of these asks is the project's own arming
rule (a code PR arms by its work-commit count); the word is for what
that rule leaves to the owner. Decided by the owner, 2026-09-18.

## A cut delivery is partial

A transport may cut a delivery to fit its notification and append the
means of reading the rest (the reference implementation ends such a
delivery with its `--replay <seq>` line). A delivery that ends that way
is partial by definition: the recipient replays it before answering
anything that carries `ACCEPTANCE`, `BY`, `FOLD-BY`, `DELIVER-TO` or a
sha range, because those are exactly the sections that sit past the
cut. A reply to the visible part is a reply to a message the sender
did not write.

## When the relay is down

The relay is one process and can be gone for a while; the watch says
once when it drops and once when it returns. While it is down, a
message carrying `BY` or `FOLD-BY` — a clock is running on it — goes by
the human relay at once (HUMAN-RELAY-TRANSPORT.md) rather than queueing
behind the outage, and the sender says so in the body when the relay
returns, so the two carriers' records agree.

## Role is not authentication

`ROLE: Application Architect` is a self-description. The transport adapter authenticates a native sender identity according to local channel policy. Organizational trust in that identity is a deployment concern, not a wire-format claim.

## Role is not identity

A role is a classification shared by however many instances currently hold it; the instance is the peer. Only `host/instance` identifies a peer. `TO-ROLE` addressing is therefore one-to-many, and a reply to "the Backend Engineer" is a reply to whichever instance answered, not to the role.

## Git context is descriptive

`BRANCH` and `COMMIT` help peers reproduce the sender's context. They never imply exclusive ownership.

A `REPLY` whose `REFERENCES` name a branch or pull request says where its
sender is working. That is a report, not a reservation: it does not stop
another instance from working on the same thing, and a branch name alone
does not commit the sender to finishing. What a sender undertakes it says
in words (MESSAGE-FORMAT.md, "Working on a request together") — an
agreement between agents, changed by saying so, never a lock the protocol
enforces. A peer that reads it decides for itself.

# ADR-044 — Identity kinds: an agent and a human

**Date:** 2026-10-08
**Status:** Proposed
**Decision Makers:** the owner (a human login as an identity of the fleet); drafted by fabric-coordinator
**Scope:** what a placed login is (`runtime/hosts/registry.json` `kinds`); what each kind holds and runs; `fabric-ctl`'s fleet-wide reads; provisioning a human login (`runtime/provisioning/new-agent.sh`); Fleet Deck's operator login (herdr)
**Pillar:** P1

## 1. Context and Problem

Every placed login has been an agent: a Linux account that runs a Claude
session under a bound role, with a control agent (agentd), a launcher, a
Claude account and a launch prompt. Fleet Deck, the terminal workspace
in which the owner watches and re-enters every agent's tab (herdr), needs
a login of another sort. It runs herdr's server and socket, enters
accounts with `moveto` (which needs that login's sudo grant), and reads
the fleet's session states. A person sits at it; no agent runs there.

The deck's design (architect-cto, 2026-10-07) first said it "runs as the
operator", which on this host was the coordinator's own login. That is
wrong twice. The deck would carry the operator's signing key, which can
act on every account, though it only reads. And it would tie a person's
terminal to an agent's account. The owner's answer was to make the
person's login an identity of the fleet, like an agent's, of a different
kind.

## 2. Decision

A placed login has a kind: `agent` (the default) or `human`. Both are
Linux logins: the identity invariant holds for both, and a human's login
is its name as an agent's is. Both have an agent id, a store of their
own and a key certified by a parent. A human runs no session, no
launcher, no agentd and has no Claude account. It holds what its work
needs: a relay credential to read the fleet's state stream and to send
GZCoord messages as itself, and the grants the host gives it (moveto's
sudo for an operator). It holds no signing key for the control plane,
unless the owner gives one to the owner's own login.

## 3. Alternatives Considered

- **The deck on the coordinator's login.** It would hold the operator
  key it never needs, and a person's terminal would share an agent's
  account. Rejected.
- **The deck on an unplaced login.** It could not read the state stream
  (the relay's token is a placed login's) or be named in a message,
  presence or a review. Rejected.
- **A read-only states file the daemons publish for the host.** It
  would work for one host only, and adds a second record of the states
  beside the stream. Rejected; the placed human login reads the stream
  itself.

## 4. Rationale

The fleet's authority already rests on the login, not on what runs in
it. A kind says what a login runs, so the tools that assume an agent
(fabric-ctl's fleet-wide ops, which ask every account's agentd; the
launcher; the drain) can leave a human out by reading one field, instead
of failing on it as "no answer". And a person who coordinates becomes
visible as one: in messages, in presence, in a review's provenance.

## 5. Binding Rules

1. `runtime/hosts/registry.json` `kinds` maps a placed login to its
   kind, `human`; a login it does not name is an `agent`. Lint refuses a
   kind other than `agent` or `human`, and a kind for a login not in
   `placement`.
2. A human login has an agent id, a store of its own and a key its
   parent certifies, as an agent does (ADR-038, ADR-039). It has no
   Claude account, no role binding, no launcher, no agentd and no launch
   prompt, and none is provisioned for it.
3. A human's store holds the relay credential the deck's reads and its
   messages need. It holds the control plane's signing key only when the
   owner gives it to the owner's own login.
4. `fabric-ctl all` asks only agents: a human has no agentd to answer.
   A human is named in what fabric-ctl prints as a human, never as a
   silent account.
5. A human login enters an agent's account only with `moveto` and the
   host's sudo grant for it; it never becomes an agent's role account,
   and no agent becomes a human's (ADR-010 rule 12).

## 6. Consequences

- Fleet Deck runs on a human login with exactly what it needs, and the
  operator's signing key stays with the coordinator.
- Provisioning gains a path: new-agent for a human makes the login, its
  key and store, and its relay credential, and none of a session's
  pieces.
- A person's messages over GZCoord carry a placed address, so a reply
  reaches them and a review can name them.

## 7. Future Evolution

A human login that should act on the fleet (arm, distribute) could hold
a signing key of its own instead of the operator's, once a second
person operates the fleet. Presence could report a human as present
when its deck is running.

## 8. Decision Status

Proposed. It is accepted when the owner merges the pull request that
carries it. The `kinds` field, fabric-ctl's skip and the lint land with
it; provisioning a human login follows in its own pull request.

## References

- ADR-010 (hosts and the one-way sudo rule), ADR-029 (the control plane;
  the state stream, rule 16), ADR-038 (each identity's key and store),
  ADR-039 (the agent id).
- `docs/fleet-deck/session-recovery.md`: the plan this serves.

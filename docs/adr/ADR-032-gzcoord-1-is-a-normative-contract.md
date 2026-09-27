# ADR-032 — GZCOORD/1 is a normative contract: the grammar frozen until a transport exercises it, GZCOORD/2 for a breaking change, adoption by observation

**Date:** 2026-09-13
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #53 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** communication/gzcoord/protocol/ (SPEC.md, MESSAGE-FORMAT.md, SEMANTICS.md, CONFORMANCE.md, examples/); the reference validator communication/gzcoord/scripts/gzmsg.mjs and communication/gzcoord/tests/protocol.test.mjs; fabric-coordinator's authority over the protocol (identities/roles/fabric-coordinator/charter.md, "The GZCoord protocol"); how a protocol change is proposed, judged and recorded
**Pillar:** P5

## 1. Context and Problem

GZCoord is the message protocol every session uses to reach another:
`[GZCOORD/1] TYPE`, a `KEY: value` metadata block, named sections. It
came into agent-fabric from the first managed project when the control
plane was extracted on 2026-09-13, with the role that owned it (now
fabric-coordinator) and a charter that already treated it as a contract:
conservative by default, the grammar frozen, a breaking change only under
a new marker.

Since then the text has been tightened many times — the assignment rule
of 2026-09-19 (ADR-023), the secrets rule, `MESSAGE-ID` made mandatory,
`HELLO` and `GOODBYE` deprecated on 2026-09-25 (ADR-030) — each time
under the same constraints, which were written only in the coordinator's
charter and SPEC §18. Every concurrent session parses what the others
send: a protocol that changes freely breaks more than one that stays
still, and a change made in the spec with nothing recording why reads,
to the next coordinator, as a free edit.

## 2. Decision

**GZCOORD/1, as written in `communication/gzcoord/protocol/` — SPEC.md,
MESSAGE-FORMAT.md, SEMANTICS.md and CONFORMANCE.md — is the normative
contract** every agent-fabric session, validator and runtime conforms to.
The four files are the contract's text; this record governs how that text
may change.

- **The grammar is frozen until an automated transport exercises it.**
  "Grammar" is SPEC §6: the header line, the `KEY: value` form, the
  section markers. A human relay proves the semantics and the message
  shapes, not the grammar under load, ordering, loss or concurrency.
  Meanwhile, clarified prose, conventions, recommended shapes, tightened
  MUSTs on existing fields and new optional common fields are in scope;
  a new message type or a changed metadata grammar waits.
- **Within GZCOORD/1 the accepted set only narrows.** Every message valid
  under the core rules of the current text was valid under every earlier
  GZCOORD/1 text. A tightened MUST retires a shape and names the field at
  fault; it never redefines one.
- **GZCOORD/2 for a breaking change.** A change that would make an old and
  a new reader disagree about a message both accept, or that widens §6 so
  an old reader cannot parse what the new text accepts, needs the new
  marker (SPEC §18). A narrowing never does: a new marker makes every
  GZCOORD/1 reader reject every message, including the ones the narrowing
  never touched.
- **Adoption by observation.** A proposed change earns adoption by being
  observed, not argued: it recurs across independent sessions, it fixes a
  real interoperability failure rather than a preference, and it is the
  smallest change that fixes it. Where relay traffic exists, live messages
  are the evidence; where it does not, what git and pull requests show
  about how sessions coordinate.
- **Every change to the text is recorded here.** A change to SPEC.md,
  MESSAGE-FORMAT.md, SEMANTICS.md or CONFORMANCE.md lands with an
  amendment of this record in the same pull request.

## 3. Alternatives Considered

- **A living document, iterated freely.** Rejected: every session is a
  parser of every other's messages, and each silent reinterpretation is
  an interoperability failure found later, by someone else.
- **Version every change** (GZCOORD/1.1, /1.2 …). Rejected: a marker is
  what a reader checks at the first line to decline what it cannot read;
  bumping it for a narrowing makes readers reject messages they would
  have read correctly.
- **Unfreeze the grammar now.** Rejected: nothing automated exercises it
  yet. The one automated transport attempted before the relay, Telegram,
  was retired (`communication/gzcoord/history/telegram-transport/`); the
  relay moves text without depending on the grammar's edge cases.
- **Record the protocol's decisions only in the spec and the charter.**
  The state before this record. Rejected: the reasons for a tightening
  lived in commit messages, and the charter is not where a reader of the
  protocol looks.

## 4. Rationale

A contract that many independent sessions depend on is worth more stable
than improved. The narrowing-only rule gives the protocol a way to learn
— every shape that once shipped broken can be refused, with the field
named — without ever making an old reader wrong about a message it
accepts. The observation bar keeps the text from growing by argument, and
the amendment rule gives each change the same trail every other decision
of the fabric has.

## 5. Binding Rules

1. The four files in `communication/gzcoord/protocol/` are GZCOORD/1's
   normative text; `communication/gzcoord/scripts/gzmsg.mjs` is the
   reference validator, and `communication/gzcoord/tests/protocol.test.mjs`
   holds it to the text — every file in `protocol/examples/` and every
   inline example in MESSAGE-FORMAT.md validates under the deployment's
   role catalogue.
2. Only fabric-coordinator changes the four files (ADR-018). Any other
   role proposes — a GZCoord `REQUEST` to the coordinator, or a pull
   request it does not merge.
3. The grammar (SPEC §6: the header line, the `KEY: value` form, the
   section markers) does not change until an automated transport
   exercises it. A new optional common field is not a grammar change: §6
   already requires a parser to preserve unknown metadata. A new message
   type waits; an extension uses an `X-` name (SPEC §10).
4. Within GZCOORD/1 a change only narrows the core accepted set; a
   tightened MUST is enforced by the validator with the field at fault
   named. A deployment profile — the role catalogue, identifier minting —
   is outside this guarantee and is the deployment's own (SPEC §4, §18).
5. A change that makes an old and a new reader disagree about a message
   both accept, or that widens §6 beyond what an old reader parses, is
   `GZCOORD/2`, never an edit to GZCOORD/1; a narrowing is never
   `GZCOORD/2`.
6. A change is adopted only when it recurs across independent sessions or
   interactions, fixes a real interoperability failure, and is the
   smallest change that does; the amendment names the evidence.
7. A change to SPEC.md, MESSAGE-FORMAT.md, SEMANTICS.md or CONFORMANCE.md
   lands with an amendment of ADR-032 in the same pull request, saying
   what changed, under which of rules 3–5 it falls, and the evidence of
   rule 6. An editorial fix to those files (a typo, a renumbered
   citation) carries an `ADR-Editorial:` trailer instead.
8. The examples and the validator change in the same pull request as the
   text they illustrate or enforce.

## 6. Consequences

- A protocol change costs a record amendment beside the text: the price
  of a trail, paid once by the writer.
- SPEC.md's own header still reads `Status: Draft`, and nothing in the
  four files names this record; the protocol is normative by this
  decision, and the header's wording changes with the first amendment.
- The freeze holds until an automated transport exists; with the relay
  as the only transport, the grammar stays as it is.

## 7. Future Evolution

An automated transport that exercises the grammar — ordering, loss,
concurrency — reopens rule 3; what it shows is the evidence rule 6 asks
for. `GZCOORD/2` is expected only when a change cannot be made as a
narrowing.

## 8. Decision Status

Accepted. The freeze, the narrowing rule, the marker and the observation
bar are practised; rule 7 binds every change to the four files from this
record on.

## References

- `communication/gzcoord/protocol/SPEC.md` (§4, §6, §10, §18),
  `MESSAGE-FORMAT.md`, `SEMANTICS.md`, `CONFORMANCE.md`, `examples/`.
- `communication/gzcoord/scripts/gzmsg.mjs` (`validate`),
  `communication/gzcoord/tests/protocol.test.mjs`.
- `identities/roles/fabric-coordinator/charter.md` §"The GZCoord
  protocol".
- `communication/gzcoord/README.md`.
- ADR-018 (authority), ADR-023 and ADR-030 (tightenings made under these
  rules), ADR-024 (a message is advisory).

## Amendments

The body above reads current; each change's full note is in [history/ADR-032-amendments.md](history/ADR-032-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-27 | HELLO and GOODBYE retired | SPEC §5, §8, §10, §11, §14, §18 and the companion texts: the two types are retired, a narrowing under rule 4 with the evidence of rule 6 |

# ADR-035 — Federation between organizations: expertise transfers, confidential information does not; portable trust first

**Date:** 2026-09-27
**Status:** Accepted
**Ratified:** owner, 2026-09-29, "Accept", answering fabric-coordinator's question closing the Proposed records; carried by the pull request that marks them Accepted
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** how agent-fabric would let one organization work with another: what may cross the boundary, what never does, and the trust that must exist first; no tool, file or practice is changed by this record
**Pillar:** P6

## 1. Context and Problem

ADR-000's P6: autonomous organizations bring in outside expertise, agree
on responsibilities and exchange results, each keeping control of its own
resources and information; transferring expertise never means
transferring confidential information. Its Today: "Nothing federates
yet." It names the precondition: before two organizations can
collaborate, identity, signed actions and provenance must be verifiable
across the boundary without sharing credentials or private memory, and
the signed control-plane actions and the rule that a login is an
identity are the seed.

What exists today, read from the tree, and where each stops at the
boundary of one installation:

- **Identity** is the login on a host; an address is `<host>/<login>`
  (ADR-002). A host's id is its short hostname, unique within one
  `runtime/hosts/registry.json` — nothing makes it unique between two
  organizations, and nothing in an address names an organization.
- **Signed actions**: a control-plane action carries an Ed25519
  signature, verified against the operator's public key committed in the
  hosts registry (ADR-009, ADR-029). Replies are not signed. Only an
  account of the same installation, reading the same registry, verifies.
- **Messages** are unsigned; the relay authenticates with one bearer
  token every account holds, and its `sender` field is a claim (ADR-033).
- **Commits**: every account commits under one git author; the lane is
  named by a `Fabric-Role:` trailer the hooks write (ADR-018) — it names
  a role, not a login, and only the installation's own CI checks it.
- **Provenance of knowledge**: every slice carries `origin` (agent, host,
  project, working copy) written by the assembler (ADR-013 §5 rule 6) —
  a claim of the installation that assembled it.
- **The confidentiality boundary**: a project's knowledge lives in the
  project's own repository, under its own licence
  (`projects/registry.json` records each licence; five are proprietary),
  never in the fabric's corpus (ADR-013). The fabric's field knowledge
  (`memory/domains/`, `memory/shared/`), charters and skills are
  Apache-2.0. The lint that refuses a managed project's name in a generic
  file covers the fabric's code, skills and role definitions, not
  `memory/`.

## 2. Decision

**Federation is built trust-first, and expertise is what
crosses.**

- **What crosses the boundary** is expertise and results: field
  knowledge, practices, role definitions and skills, and the artifacts an
  engagement produces for the other side (a pull request, a report, a
  review), each under the licence it already carries.
- **What never crosses**: a project's code and knowledge outside that
  project's own access and licence, an agent's private memory, a
  credential, a secret, the content of a relay channel.
- **Portable trust first.** No exchange between organizations is built
  before its three kinds of trust are verifiable by the other side from
  a published record, with no shared credential:
  1. *identity* — an address qualified by its organization, resolvable
     to a public key the organization publishes;
  2. *action* — a request or a result signed by that key;
  3. *provenance* — who produced a piece of knowledge or an artifact,
     signed the same way.
- **Each organization keeps control of its resources.** A request from
  another organization is advisory, as every GZCoord message is
  (ADR-024); the receiving organization's own agents decide and act, and
  no key of one organization orders anything on the other's accounts.

## 3. Alternatives Considered

- **One installation for both organizations** — shared relay, shared
  registry, accounts side by side. Rejected by P6 itself: organizations
  collaborate "without becoming one installation", and one registry would
  give each side the other's operator.
- **Exchange first, trust later** — a shared channel with a shared token,
  as the relay works inside one installation. Rejected: a shared token is
  exactly the credential P6 says is not shared, and every claim on such a
  channel is unverifiable to the other side.
- **Federate knowledge by copying the corpus.** Rejected: provenance
  would be the copier's claim, and a slice's origin names agents and
  projects the receiving side cannot verify.

## 4. Rationale

The fabric already separates what must not travel from what may: a
project's knowledge is in the project's repository, the field knowledge
is the fabric's and openly licensed, and an identity is a login rather
than a credential. What is missing is only the ability of an outsider to
check a claim — and every existing mechanism (signed actions, slice
provenance, the role trailer) is a claim that one installation can check
of itself. Making those checkable from outside comes before any exchange,
because an exchange built on unverifiable claims would have to be torn
down to add them.

## 5. Binding Rules

1. Nothing a managed project keeps — code, `.agent-fabric/`, issues,
   channel traffic — leaves that project's access and licence through a
   federation mechanism. An agent's private memory and any credential
   never leave the account.
2. What another organization may receive is fabric-scope knowledge,
   practices, role definitions and skills under this repository's
   licence, and the artifacts of an engagement delivered to it.
3. No federation mechanism uses a credential held by both sides.
4. An exchange is built only after identity, action and provenance are
   each verifiable by the other organization from a record it can fetch.
5. A request between organizations is advisory; no signed action of one
   organization is accepted by the other's control agents.
6. Before the field corpus is offered outside, the check that keeps a
   managed project's name out of generic files is extended to
   `memory/domains/` and `memory/shared/`, or the corpus is reviewed for
   project-specific content by another means.

## 6. Consequences

- Nothing changes today; the record orders the work that would.
- An organization-qualified address is a GZCoord question: a new field
  or a changed address form is bounded by the protocol's freeze
  (ADR-032), so federation traffic may need a carrier-level identity
  first.
- Signed replies (ADR-029 §7) and signed messages become prerequisites,
  not refinements.

## 7. Future Evolution

**The first concrete step:** publish, per installation, a record of its
organization's identity — an organization id and the public keys of its
operators — and make the control plane's existing signature check verify
an action against that record rather than only against the local
registry; read back by a live check in which a second, separately
configured test installation verifies a signed action from the first and
refuses one signed by a key the record does not carry. **What would show
it worked:** that live check, and a signed action verifiable by someone
holding no credential of the signing installation.

Then: signed replies; provenance signed by the assembler's key; and only
then an exchange of expertise or results with a real second organization.

## 8. Decision Status

Accepted and in force.

## References

- ADR-000 §5, P6 (Today, "Federation needs portable trust", Direction).
- ADR-002 (the login is the identity), ADR-009 and ADR-029 (signed
  actions), ADR-013 (scopes, provenance), ADR-018 (the role trailer),
  ADR-024 (messages are advisory), ADR-032 (the protocol's freeze),
  ADR-033 (the relay's shared token).
- `runtime/hosts/registry.json` (`operator_key`),
  `runtime/control/sign.mjs`, `projects/registry.json` (`license`),
  `tools/fabric/lint.py` (`project_name_findings`, `GENERIC_DIRS`).

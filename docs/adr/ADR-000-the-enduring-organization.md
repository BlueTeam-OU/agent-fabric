# ADR-000 — The enduring organization

**Date:** 2026-09-27
**Status:** Accepted
**Ratified:** owner, 2026-09-27, "merge 50" — the owner's word to the fabric-coordinator session, arming agent-fabric #50
**Decision Makers:** the owner (the vision, and the coordinator's proposals adopted into it); drafted by fabric-coordinator
**Scope:** what agent-fabric is for, the principle every other decision serves, and the pillars the decision records are grouped under
**Pillar:** all

## 1. Context and Problem

agent-fabric began as the control plane for a team of AI agents working on
a few repositories: who each agent is, which role it holds, how its models
are routed, how the agents talk. Two weeks of operation produced a great
deal of machinery, and the question of what it is all *for* was answered
only implicitly — in one note per changed concept, with no index, and in
decisions that lived in commits, JSON descriptions and the coordinator's
memory.

The owner stated the purpose on 2026-09-27. This record is the
coordinator's paraphrase of that statement, which the owner ratified by
arming it; the owner's own text is kept verbatim beside it, in
`docs/adr/sources/ADR-000-the-owners-statement.md`. Every other decision record
in this directory serves the purpose stated here and is grouped under one
of its pillars.

## 2. Decision

agent-fabric is **infrastructure through which people and agents build
enduring organizations**: organizations that accumulate experience,
exercise judgement and keep their autonomy over time — not merely
persistent teams of agents. The promise is not more intelligence on tap;
it is **turning temporarily available intelligence into lasting
collective capability**.

One principle runs through every part of it: **separate what must endure
from what must be able to change.** Identity is not the model. Expertise
is not a session. Collaboration is not an orchestrator. A project's
knowledge does not belong to the infrastructure that serves it.

Humans stay in the organization. They set its direction, its constraints
and its fundamental choices, and they judge its results; they stop being
the manual connection between every two activities. Software development
is the first proving ground. The broader aim is that even a small
organization can *sustain* its projects over time — without rebuilding
expertise and coordination each time something changes.

## 3. Alternatives Considered

- **A well-configured team of agents** — prompts, tools and models tuned
  for today. Rejected as the goal: every change of model, host or member
  would be a rebuild, and nothing learnt would outlive the configuration.
- **A central orchestrator** that plans, assigns and schedules the agents'
  work. Rejected: it moves judgement out of the people doing the work, and
  it makes the organization only as available as the orchestrator. The
  control plane provides tools and keeps boundaries; it does not set the
  agenda (pillar P3).
- **Memory as a transcript of everything said.** Rejected: an organization
  that remembers every conversation still repeats its mistakes. What must
  last is curated knowledge, practice and the ability to apply them
  (pillar P2).

## 4. Rationale

The separations — the six things `CLAUDE.md` keeps apart (agent, role,
project, working copy, host, session), and the model beside them — were
drawn early and have held under pressure: a role moved
between accounts, a model family replaced under running work, a host
crash, a provider change. Each time what survived was exactly what had
been kept apart from the thing that changed. Naming that principle — and
naming the pillars it implies — turns an accident of good design into a
criterion every future decision can be tested against: *does this make
what must endure depend on what will change?*

## 5. Binding Rules

1. Every decision record in `docs/adr/` names the pillar it serves
   (`**Pillar:**`), from this table. The table is the only list of
   pillars; `tools/fabric/adr.py` reads it from here.

   | Pillar | Name | In one line |
   |---|---|---|
   | P1 | Outlives its tools | Changing a model, a host or a member upgrades the organization; it does not rebuild it |
   | P2 | Learns, not merely remembers | Every project leaves the team more capable than it found it |
   | P3 | Autonomy with verifiable commitments | Agents coordinate among themselves; what they agree reaches an artifact |
   | P4 | Diversity of expertise | No problem is forced into a single perspective; the team can correct itself |
   | P5 | Autonomy from infrastructure | A failure or a provider change may reduce capacity, never identity, knowledge or continuity |
   | P6 | Federation | Organizations collaborate without becoming one installation or sharing what is confidential |
   | P7 | Sustainable operation | The organization lives within finite means and spends them cooperatively |

2. Each pillar below is stated as **Today** — what exists, citing the
   record that holds it once that record is written — and **Direction** —
   what does not exist yet. A
   direction is never presented as an accomplished result.
3. A decision that makes something that must endure depend on something
   that will change needs an explicit justification in its §4.
4. This record changes only by an amendment carrying the owner's words.
   Adding, merging or retiring a pillar is such an amendment.

### P1 — Outlives its tools

**Today.** The Linux login is the agent; the filesystem is context; the
role is bound, not inferred (ADR-002). Models are chosen by capability
class, never by a vendor name in an agent's instructions, and every class
moved to a new model family without a single agent being rebuilt (ADR-005). A host crash and a fleet-wide upgrade left every
agent's identity and memory in place (ADR-009, ADR-010). A role's charter,
brief and distilled knowledge belong to the role, so assigning it to
another agent transfers the professional knowledge without confusing the
individual with the function.

**Direction.** Changing models upgrades the capabilities available to the
team instead of rebuilding it; moving an agent to another host does not
erase its history; assigning a role to another agent transfers the
professional knowledge without confusing the individual with the function.
Moving a host becomes a routine operation, not a
procedure, and a new model family is adopted by a routing change and a
measured read-back, and nothing else.

### P2 — Learns, not merely remembers

**Today.** Knowledge is kept by scope — the field, the system, the
individual — and by kind: what a system implements, why a decision was
made, how the work is done, what is still open. It is written by
whoever learnt it, drained with provenance, and curated rather than
accumulated; a newer fact in the tree outranks an older claim, and a
formalized decision outranks reasoning left in memory. A costly mistake
becomes a guard that checks for it; a working method becomes a
practice every role reads.

**Enduring is not unchanging.** An organization
endures because it can retire what it believed. Every standing decision
carries its revision path (amendment, supersession — ADR-001) and the
evidence it rests on (live checks). A belief with neither
evidence nor an owner is a liability, not an asset.

**Direction.** Every project leaves a precaution, a method or a corrected
belief behind it, found where the next project will look. Learning
resides in curated knowledge and practice; it does not require changing
any model's weights. A decision whose evidence has
gone stale is flagged for review, not kept on inertia.

### P3 — Autonomy with verifiable commitments

**Today.** The control plane supplies tools, identity and boundaries; the
agents divide the work, negotiate dependencies and revise their
agreements among themselves. Operating within a role is
separate from the power to redefine it. A conversation is not a
decision until it reaches an artifact — a pull request, a contract, a
decision record.

**Verification over assertion.** Trust is earned by
what can be checked, not by who said it: the repository outranks the
message, a claim cites its artifact, review is blind so the author does
not grade their own work, and a measurement comes before a
belief.

**An explicit mandate, not implicit supervision.**
Autonomy is bounded by a mandate the humans set and the agents can read:
what an agent decides alone, what needs the role's owner, what needs the
owner's word. Today that mandate is scattered — the arming band, the
ratification of records, the authority guard, the carried owner's word.

**Direction.** Progress is measured by how much less supervision a
correct, verified and maintainable result needs, not by how many
messages the agents exchange. The mandate is
stated as a whole, so that "ask the owner" is a rule and not a reflex, and
supervision falls without any loss of control.

### P4 — Diversity of expertise

**Today.** Roles span development, databases, networking, communication,
tooling and language-and-culture. The language-culture role separates
composition in the local language from its rendering for the rest of the
team, and is explicit that observing texts does not establish the
language in which reasoning happens. Reviews are independent of
the author.

**Direction.** The domain specialist can challenge a technically elegant
solution unsuited to its use; the communication specialist can name a
promise the product does not keep; the language-and-culture specialist
shapes the experience instead of translating it at the end. The team's
value lies not in always agreeing but in being able to correct itself.

### P5 — Autonomy from infrastructure

**Today.** Each account has an operational presence that needs no model
session: a control agent answering over the relay, signed actions for
fleet operations (ADR-009). Presence is read from each account's
process table, not from what a session announced. The GZCoord
relay is, today, **central**: one process on one host.

**Failure is expected and survivable.** Sessions end,
relays drop, hosts crash, providers change. Work and agreements are
resumable by whoever comes next from artifacts, not from conversation; a retry keeps its message id; the control plane keeps
answering when a model does not.

**Direction.** Decentralization where it produces real autonomy and
resilience, not complexity for its own sake. The criterion: a
failure or a change of provider may reduce the team's capacity for a
while; it must not take its identity, its knowledge or its ability to go
on working. Dependence on one person is not replaced by dependence on one
central service. Every operation the organization
depends on has a documented degraded mode.

### P6 — Federation

**Today.** Nothing federates yet. The separation this pillar needs exists:
shared infrastructure is kept apart from each project's knowledge, which
stays in the project's own repository within its own access and licence
boundaries.

**Federation needs portable trust.** Before two
organizations can collaborate, identity, signed actions and provenance
must be verifiable across the boundary without sharing credentials or
private memory. The signed control-plane actions and the rule that a
login is an identity are the seed.

**Direction.** Autonomous organizations bring in outside expertise, agree
on responsibilities and exchange results, each keeping control of its own
resources and information: a federation of capabilities, not one central
intelligence. Transferring expertise never means transferring
confidential information.

### P7 — Sustainable operation

**Today.** The organization runs on finite means: model budgets and usage
windows, prompt and context budgets, a host's disk and memory, and the
owner's attention. Shared host resources are leased (ADR-010); a test run
leaves nothing behind; launch prompts have a ceiling and prompt
templates a token budget; the host crashes under test load
(`docs/live-checks/2026-09-19-develop-qzapp-crash.md`,
`docs/live-checks/2026-09-25-develop-qzapp-crash.md`) are why.

**Direction.** A cost per verified result is measured beside the
supervision per verified result. Growth is judged by capability
per unit of spend, not by the number of agents; consuming a shared
resource is a cooperative act, like any other commitment.

## 6. Consequences

- Every decision record has a place and a reason to exist; one that serves
  no pillar is a sign the pillars are wrong or the decision is.
- The vision is testable: a later decision can be refused for making what
  must endure depend on what will change (rule 3).
- The directions are public commitments. Stating them with their "today"
  makes the gap visible, which is the point.

## 7. Future Evolution

The owner amends this record when the purpose moves; any part of it,
whoever first proposed it, is changed or struck by amendment without
touching the rest. The first
directions expected to become records of their own are the supervision
measure, decentralization, federation and
sustainable operation.

## 8. Decision Status

Accepted: the owner armed the pull request that introduces it (agent-fabric
#50, "merge 50") after being told that arming ratifies this
record, its then-marked proposals included.

Whose words these are. The purpose, the principle, and pillars P1–P6
with their directions are the owner's statement, paraphrased (the source
is kept verbatim, References). Pillar P7, five paragraphs and four
sentences that began as the coordinator's proposals, the alternatives of
§3 and the structural rules 2–4 of §5 were drafted by the coordinator;
the owner adopted the proposals into the vision
(Amendments), so the body no longer marks them. The **Today** paragraphs
are the coordinator's account of what the tree holds, checkable against
it.

## References

- `docs/adr/sources/ADR-000-the-owners-statement.md` — the owner's statement of
  the vision, 2026-09-27, verbatim.
- ADR-001, the decision records themselves.
- `CLAUDE.md` §"Six things that are kept apart" and `README.md` — the
  separations this principle names.

## Amendments

The body above reads current; each change's full note is in [history/ADR-000-amendments.md](history/ADR-000-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-27 | The coordinator's proposals adopted | §5 P1–P7: the proposal markers removed, P7 a pillar like the others; §7, §8 and the header say so |

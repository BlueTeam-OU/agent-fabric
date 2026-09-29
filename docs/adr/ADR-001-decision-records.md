# ADR-001 — Decision records

**Date:** 2026-09-27
**Status:** Accepted
**Ratified:** owner, 2026-09-27, "merge 50" — the owner's word to the fabric-coordinator session, arming agent-fabric #50
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** docs/adr/ — how agent-fabric records, amends and supersedes its decisions; tools/fabric/adr.py; who writes and who accepts
**Pillar:** P2

## 1. Context and Problem

Until 2026-09-27 agent-fabric recorded a decision as a note under `docs/`
"when a concept changes meaning" (the coordinator's charter). Nineteen
such notes, twenty-three live checks, the protocol files and a dozen
READMEs accumulated with no index and no rule for how a decision changes.
The survey of that day found notes contradicting the tree (commits said
to go straight to main; HELLO still taught after its retirement), one
decision filed inside a measurement, rules repeated in three and four
places, and about twenty-five decisions recorded nowhere but in commits,
JSON descriptions, the launch prompt or the coordinator's own memory.

gzapp, the first managed project, has kept architecture decision records
since 2026-06: numbered files, a master index, a digest read first, and an
amendment model in which the body always reads current and each change's
note goes to a history file (gzapp's ADR-075). Its validator enforces the
index, the numbering and the amendment bookkeeping; the section structure,
the ratification of a decision and the index itself are convention there.
The owner asked for the same engine here.

## 2. Decision

agent-fabric records its decisions as numbered decision records in
`docs/adr/`, on gzapp's engine, with what gzapp leaves to convention made
checkable by `tools/fabric/adr.py`:

- `ADR-NNN-kebab-title.md`, contiguous from ADR-000; the header fields
  Date, Status, Ratified (when Accepted), Decision Makers, Scope, Pillar,
  and optionally Evidence; the sections §1 Context and Problem to §8
  Decision Status, References, and `## Amendments` last.
- **Amendment**: the body is edited in place so it always reads current,
  with rule numbers permanent; the full note goes to
  `history/ADR-NNN-amendments.md` under `### Amendment YYYY-MM-DD —
  Title`; the ADR's Amendments table gets the same (date, title) row; the
  DIGEST entry gets an `A YYYY-MM-DD` bullet.
- **Supersession**: a new ADR; the old one's body freezes, its status
  names the successor and it carries a point map of where each rule now
  lives.
- `index.json` and the README's index table are **generated** from the
  headers; `DIGEST.md` is written by hand, looked up (`fabric-adr
  lookup <topic>`, or the table alone with no topic) and never read
  whole, and loses to the ADR when they disagree. An entry is at most
  250 words, which `adr.py check` enforces, so a lookup stays a few
  hundred tokens (A 2026-09-29).

## 3. Alternatives Considered

- **Keep one note per concept, add an index.** Cheaper, but it keeps the
  failure that made the notes rot: nothing says how a note changes, so
  they drifted from the tree unnoticed.
- **Copy gzapp's tooling (Node).** agent-fabric's checks are Python in
  `tools/fabric/`; one language for the fabric's guards outweighs sharing
  a file with a project that owns its own copy.
- **A different prefix (FDR-NNN)** to avoid colliding with gzapp's
  numbers. The owner chose plain `ADR-NNN`, with the repository named in
  every citation from outside it (rule 6).

## 4. Rationale

A decision record is where a conversation becomes binding (ADR-000, pillar
P3) and where a belief can be retired instead of accumulated (pillar P2).
Both need the record to be findable, current and honest about its
history, which is what the index, the amendment model and the ratification
line give. The engine is proven on 77 records in gzapp; the additions here
are exactly its known weak points — an index described as generated but
maintained by hand, two amendment heading forms accepted, no structural
check, and nothing making ratification visible.

## 5. Binding Rules

1. Only fabric-coordinator writes `docs/adr/` (the authority guard already
   refuses any other role in this repository). Other roles propose by a
   GZCoord REQUEST to the coordinator, or by a `rationale` slice in their
   own memory; a conversation alone never changes a record.
2. Only the owner accepts. A record is `Accepted` only with a `**Ratified:**
   owner, YYYY-MM-DD, <source>` line naming where the owner's word is — a
   commit, a relay message, a pull request. Merging a pull request ratifies
   the already-practised records in it, and a new
   record only when the description says arming ratifies it and the owner
   arms it on that basis — as agent-fabric #50 did for ADR-000 and ADR-001.
   Any other new direction stays Proposed until the owner accepts it
   individually.
3. A decision is made or changed by a record: the coordinator writes a new
   ADR, amends one, or supersedes one — never a free-standing note.
4. An amendment is the triple of §2, in one commit series, with the
   rationale in the commit body. A commit that edits an ADR's body without
   an Amendments row carries an `ADR-Editorial: <why>` trailer (a typo, a
   renumbered citation); `adr.py range-check` refuses anything else in CI.
5. `index.json` and the README index table are never edited by hand;
   `tools/fabric/adr.py index --write` regenerates them, and a stale copy
   fails `adr.py check`.
6. Outside agent-fabric, a citation always names the repository —
   "agent-fabric ADR-NNN" — because a managed project may keep ADRs of its
   own under the same numbers. Inside `docs/adr/`, a bare ADR-NNN is this
   repository's and must exist; another project's is written with its
   name ("gzapp's ADR-075").
7. A fabric-scope `rationale` slice is promoted into an ADR by the
   coordinator; a project-scope one belongs to that project's own records.
   The promoted slice is corrected by its author's next memory ("promoted
   to agent-fabric ADR-NNN") and leaves the corpus at the next drain.
8. Live checks (`docs/live-checks/`) are evidence: immutable measurements
   an ADR cites in its Evidence field. A practice a later decision
   replaced is marked with a one-line banner; the measurement stands.
9. `docs/adr/sources/` keeps, verbatim, the texts a record paraphrases
   (the statement ADR-000 paraphrases). A source is never edited: a
   change of mind is an amendment of the record; `adr.py range-check`
   refuses any edit, rename or removal of a source, whatever the
   commit's trailers (A 2026-09-27).
10. A record's body and its DIGEST entry state the decision, not who made
    it: no attribution in parentheses naming the owner and a date.
    Who decided and when are the header's (`Date`, `Decision Makers`,
    `Ratified`) and the history's. `adr.py check` refuses a parenthesis
    that opens on the owner or the CEO (A 2026-09-27).
11. A record reads current: §2 to §8 carry no date. When a rule began is
    the header's, the Amendments table's and the history's; §1 may date
    an incident, best by citing its commit or live check. A date inside a
    path or code span and the engine's `(A …)` and `(Amendment …)` marks
    stay. `adr.py check` refuses any other date in §2 to §8 (A 2026-09-27).

## 6. Consequences

- One place answers "what has the fabric decided, why, since when".
- A decision's history is in git and in its history file, never lost to
  an in-place rewrite.
- Writing a decision costs more than writing a note: a template, a DIGEST
  entry, a pillar. That cost is the point — it is paid once, by the
  writer, instead of by every reader who has to reconstruct the reasons.

## 7. Future Evolution

The existing notes, the memory model, the protocol's decisions and the
decisions found only in memory become records in the pull requests that
follow this one; the old paths stay as short stubs until nothing cites
them. A generated DIGEST skeleton, and a check that a record's Evidence
has not been superseded, are candidates once the corpus is in.

## 8. Decision Status

Accepted: the owner armed the pull request that introduces it
(agent-fabric #50).

## References

- `tools/fabric/adr.py` — check, index, new, amend, lookup, range-check.
- `tests/test_adr.py`, `policies/check_adr_amendment.sh`.
- gzapp's ADR-075 (documentation history model) and its
  `tools/validate_adr_index/`, the engine this one follows.
- ADR-000, the pillars every record names.

## Amendments

The body above reads current; each change's full note is in [history/ADR-001-amendments.md](history/ADR-001-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-27 | A source is refused whatever the trailer | §5 rule 9: an `ADR-Editorial:` trailer no longer lets a source edit through; it excuses a record's body edit only |
| 2026-09-27 | No inline attributions | §5 rule 10 added: no parenthetical attribution in a record's body or DIGEST entry; `adr.py check` refuses one |
| 2026-09-27 | A record reads current | §5 rule 11 added: no date in §2–§8, §1 may date an incident; rule 10 loses its dated example; §8 undated |
| 2026-09-29 | The DIGEST is looked up, never read whole, and each entry has a word budget | §2: `fabric-adr lookup`; a 250-word entry budget in `adr.py check` |

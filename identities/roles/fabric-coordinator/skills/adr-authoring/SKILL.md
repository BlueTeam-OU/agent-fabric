---
name: adr-authoring
description: "How fabric-coordinator writes, amends and supersedes agent-fabric's decision records with tools/fabric/adr.py: when a record is required, the header and sections, Accepted only with the owner's word on an artifact, no attribution and no dates past §1, an amendment in the same commit as its body edit, verbatim sources, stubs for moved notes, and what a draft is checked against before review. Load it before creating or editing anything under docs/adr/, before briefing an agent to draft records, or when adr.py check or range-check refuses a commit."
---

# Writing the fabric's decision records

The engine's rules are ADR-001 §5; this is how to meet them without
learning each one from a refusal.

## When a record is needed

A decision is made or changes: a rule every session must follow, a
default, a fence, a protocol change. A record, not a note under `docs/`.
A measurement is a live check (`docs/live-checks/`), which records cite as
Evidence; a manual (a README) says how, and cites the record for why.

## The commands

```sh
python3 tools/fabric/adr.py new <slug> "<Title>"          # next number, from the template
python3 tools/fabric/adr.py amend --date YYYY-MM-DD <n> "<Title>"   # history note + table row
python3 tools/fabric/adr.py index --write                 # index.json and the README table
python3 tools/fabric/adr.py check                         # every rule below that a tool can see
python3 tools/fabric/adr.py range-check <base> <head>     # each commit's body edits are recorded
```

`check` runs in the commit hook, CI and the suite; `range-check` in CI
and the suite. Capture the exit status before committing — never
`check | tail && git commit`.

## The rules a draft must meet

- **Header:** Date, Status, Decision Makers, Scope, Pillar (from ADR-000
  §5), Evidence only for live checks that exist. `Accepted` needs
  `**Ratified:** owner, YYYY-MM-DD, <source>` naming where the owner's
  word is. A practised decision is ratified by the merge of the pull
  request that records it; a new direction stays `Proposed` until the
  owner accepts it by itself.
- **Body:** §1 Context and Problem … §8 Decision Status, References,
  `## Amendments` last. The body states the decision, never who made it:
  no parenthetical attribution to the owner or anyone. §2–§8 carry no
  date; §1 may date an incident, best by citing its live check or
  commit.
- **§5 rules** are numbered and checkable; a number is never reused. A
  withdrawn rule stays as a tombstone, a changed one carries
  `(A YYYY-MM-DD)`.
- **DIGEST:** an entry per record, the same title and status, one
  `- A YYYY-MM-DD — …` bullet per amendment.
- **Sources** (`docs/adr/sources/`) are kept verbatim: never edited,
  renamed or removed, whatever the trailer.

## Changing a record that exists at the base

Every commit that edits a record's body (from its first `## ` on) adds a
new Amendments row in that same commit (`adr.py amend`, then edit, the
note, the DIGEST bullet, `index --write`), or carries an
`ADR-Editorial: <why>` trailer when no rule changes meaning — a typo, a
citation, a sentence corrected to the tree. A change to `SPEC.md`,
`MESSAGE-FORMAT.md`, `SEMANTICS.md` or `CONFORMANCE.md` lands with an
amendment of ADR-032 in the same pull request. Superseding: a new record;
the old one's status names it and gets a point map.

## Before review: what drafts have got wrong

Check every statement against the tree now — the code, the JSON, the
hook, the test — not against the note it replaces or a memory:

- A source note that overclaims is not inherited: state what the tree
  does and name the gap.
- Every decision in a replaced note appears in the record; read the note
  line by line against the draft.
- A thread remembered as open may have been fixed: check with `git log`
  before writing "open", "planned" or "fixed".
- A rule written in several places (a record, the protocol prose, a
  skill, a manual) says the same everywhere, or the difference is named.
- Removing a date must not change a sentence's meaning.
- Records and edited files cite records, never a note the same change
  turns into a stub; a moved note becomes a three-line stub that tells
  its reader to update the reference to the record.

Then the blind review, briefed by `fabric-review brief`; P1 and P2
findings are fixed on the pull request, P3s may go to the next one.

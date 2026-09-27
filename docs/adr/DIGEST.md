# Decision digest — read first

What is true now, one entry per record. Non-normative: where an entry and
its record disagree, the record wins. `tools/fabric/adr.py lookup <word>`
searches it.

| Looking for | Record |
|---|---|
| what the fabric is for, the pillars | ADR-000 |
| how a decision is recorded, amended, accepted | ADR-001 |

### ADR-000 — The enduring organization (Accepted)

- agent-fabric is infrastructure for **enduring organizations** of people
  and agents; the promise is turning temporarily available intelligence
  into lasting collective capability (§2).
- The principle: separate what must endure from what must be able to
  change — identity ≠ model, expertise ≠ session, collaboration ≠
  orchestrator, a project's knowledge ≠ the infrastructure (§2).
- Seven pillars, each with a Today and a Direction: P1 Outlives its tools
  · P2 Learns, not merely remembers · P3 Autonomy with verifiable
  commitments · P4 Diversity of expertise · P5 Autonomy from
  infrastructure · P6 Federation · P7 Sustainable operation (§5 rule 1).
- A decision that ties what must endure to what will change must justify
  it (§5 rule 3). The record changes only by the owner's amendment (§5
  rule 4).
- Keywords: vision, purpose, pillars, principle, endure, direction.

### ADR-001 — Decision records (Accepted)

- Decisions live in `docs/adr/` on gzapp's engine: numbered records,
  amendment in place with a history note, supersession with a point map;
  the index is generated (§2).
- fabric-coordinator writes; the owner accepts, and `Accepted` needs a
  `Ratified:` line naming where the owner's word is; merging ratifies
  already-practised records (§5 rules 1–2).
- An ADR body edit needs an Amendments row or an `ADR-Editorial:` trailer
  (§5 rule 4); from outside, cite "agent-fabric ADR-NNN" (§5 rule 6).
- Live checks are immutable evidence (§5 rule 8).
- Keywords: ADR, amendment, supersede, ratify, index, digest, rationale.

# Decision digest — looked up, never read whole

What is true now, one entry per record. Non-normative: where an entry and
its record disagree, the record wins. Look it up, never read it whole:
`fabric-adr lookup <word>…` answers the entries that mention every word,
`fabric-adr lookup` alone this table.

| Looking for | Record |
|---|---|
| personal data in AI tools; Max plan; client data; privacy notice; sub-processor | ADR-059 |
| this organisation's decentralization inventory: host, relay, key, observer, providers, undrained memory | ADR-069 |
| this organisation's porting programme: Wave 10, its projects' Node scripts, mjs | ADR-070 |
| this organisation's persona naming theme: which surnames, a first name's culture, the avatar house style | ADR-071 |

### ADR-059 — Third-party personal data stays out of the Max plan (Accepted)

- The fleet keeps the Claude Max plan; no personal data of a client,
  its people or a site visitor goes into it (§2, §5 rule 1). The OpenAI
  business account is outside it; its processing agreement is offered,
  unverified, for the owner to confirm (§2).
- A 2026-10-16 — the OpenAI processing agreement is stated as offered
  and unverified, for the owner to confirm (Scope, §2).
- Work on a client's system uses cleaned data: no real commit history,
  no production access (§5 rule 2).
- The blueteam.ee privacy notice is true only while that practice is;
  a plan with a processing agreement needs a new record (§5 rules 3-4).
- Keywords: personal data, AI tools, Max, consumer plan, sub-processor,
  GDPR Article 28, privacy notice, client data.

### ADR-069 — This organisation's decentralization inventory (Accepted)

- The inventory of what this organisation's fabric depends on — one host and
  its logins, the relay and its copy, the signing key, secrets, the
  observer, providers, knowledge, undrained memory, the owner — with each
  failure's cost and degraded mode or "none" (§1).
- Kept current: a change that adds, removes or moves a dependency amends
  this record's table in the same pull request (§5 rule 1).
- The second host for GZCoord over InterWeave is fabric-h2 (Proxmox node
  s13337); the owner waived its two-host check's held bound and control
  parity report (§5 rule 2).
- Split from ADR-034, which keeps the criterion and rules 2-5 these rows are measured against.
- A 2026-11-14 — fabric-h2's InterWeave range: public forward 195.69.140.18, any source, exposure accepted by the owner; ssh stays LAN (§1 row, §5 rule 2).
- A 2026-11-28 — SPIKE-004's five limits accepted by the owner for fabric-h2's first account (the two-host check's); forward and firewall read back from outside; a dial from the provider's LAN not measured (§5 rule 2).
- Keywords: inventory, single point of failure, host, relay, degraded mode, undrained memory, decentralization table, public forward, fabric-h2.

### ADR-070 — This organisation's porting programme: its projects' Node scripts move to Python (Accepted)

- Wave 10: a managed project's own Node scripts move to Python, once, by
  the holder of the path; ported with the old script as the oracle (§1, §5 rule 1).
- A fork's upstream code, application code and a framework's own
  configuration are never ported; exemptions are named in §1's inventory.
- Split from ADR-040, which keeps rules 1-9 and waves 0-9.
- Keywords: Wave 10, mjs, Node, managed projects, port, inventory, exempt, gzapp, gzapp.decks.

### ADR-071 — This organisation's persona naming theme and house style (Accepted)

- Surnames are deceased scientists from all over the world, none who
  worked toward a weapon; where the record is mixed the owner judges (§5 rule 1).
- A language-culture agent takes a surname of its own culture; no persona
  is a famous real person's name (§5 rule 2).
- Avatars in one house style written by brand-comms: warm, hand-painted
  anime, never a named studio's (§5 rule 3).
- Split from ADR-056, which keeps the persona mechanism under rules 3, 5, 7.
- Keywords: persona, surnames, scientists, weapons test, avatar, house style, anime, first name, culture.

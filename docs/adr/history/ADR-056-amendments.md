# ADR-056 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-13 — Candidate avatars wait in a shared folder on the host

Rule 7 said where an accepted avatar goes and where rejected ones are
kept, not where a candidate waits while the agent decides: brand-comms
cannot write another agent's repository, and an image does not travel
over GZCoord. All 26 agents live on one host (runtime/hosts/registry.json),
a Qubes AppVM where /usr/local persists, so the candidates wait in a
folder there, owned by brand-comms-01, mode 0755: avatars are not secret.
The owner's word, in the coordinator's session: "put the avatar images in
the shared folder in unix filesystem".

### Amendment 2026-10-13 — An agent is named with its role as people say it, from a public directory

Rule 2 named an agent "AI <Name> (login)" where people and agents both
read; the owner: "everyone should use name surname and role (not the
slug)", and "Language, translation, localization and culture -> Culture
Specialist". The role is now the catalogue's short_title, the login only
where a machine needs it, and the first name joins the surname in
claims.json so any agent and any surface can name any other
(`fabric-persona`), not only through each agent's private profile.

### Amendment 2026-10-15 — Provisioning claims the surname; the agent chooses its sex, then a first name of that sex

Rule 4 let only the agent claim a surname, once it existed and in its
first session. On 2026-10-15 legal-expert-ee-eu was provisioned with a
surname the owner had already chosen (Kelsen), and nothing could record
it: the claim waited for a first name, and the agent could not be named
meanwhile. The owner decided that provisioning assigns the surname at
creation: `new-agent --surname <Surname>` checks it on the list and
unclaimed before anything is made, and once the account has its agent id
writes the claim with `first_name` null, which fabric-coordinator commits
with the key and the lineage. The agent still chooses its first name
(rule 5); `fabric-persona` names it "AI <Surname>, <role>" until then.

The owner added the order of the agent's own choices: "the agent choose
sex then chose name accordingly with sex". So the sex (F or M) comes
first and the first name agrees with it, from the surname's culture as
before. The sex stays where rule 1 put it, in the agent's profile, whose
schema already takes no first name without one; the claim holds no sex.

### Amendment 2026-10-16 — A claimed surname is marked taken in the list

The owner asked for the surname list to show which surnames are taken.
A claimed entry in `identities/personas/surnames.json` carries
`taken_by` with the agent id and its login, written by provisioning with
the claim and checked by lint against `claims.json` and `lineage.json`.
The claim stays the record of who holds a surname; the mark is its
reflection in the list, so a reader of the list sees what is free.

### Amendment 2026-11-12 — The naming theme and the house style move to the operator's record

Rules 3 (surnames are deceased scientists, no weapons work, the owner judges a mixed record), 5 (a first name from the surname's culture) and 7 (the house style, brand-comms, the candidates' folder) are one organisation's brand; rules 1, 2, 4, 6 and 8 are the persona mechanism and the "AI" marking ADR-033 §5 rule 3 needs. ADR-045 §5 rule 4 has a mixed record split: ADR-056 keeps its number and those five rules, and the three moved, text verbatim, into the operator's ADR-071 (there numbered 1 to 3). Their numbers stay in ADR-056 as "moved" slots, so every citation of a rule number holds. The rejected-avatar record, which sat in rule 7 and which rule 1 already pointed at, is now written out in rule 1, since the persona mechanism writes it; rule 4's "(rule 5)" for the chosen first name is "(rule 6)", which orders sex before first name. §2, §4 and the Scope say the naming theme and the style are the operator's. The owner's word is the 2026-11-11 answer on the classification (docs/split/move-plan.md §5, ADR-045's Amendments row of that date), decided in docs/split/adr-classification.md.

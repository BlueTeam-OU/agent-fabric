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

Rules 3, 5 and 7 each held a mechanism the engine runs and one organisation's taste beside it. The mechanism stays under the same numbers, which engine code cites (`tools/fabric/persona.py`, `new_agent.py`, `provisioning/surname.py`, `lint_rules/schema.py`, `avatar.py`): the list file and its entries' reasons (rule 3), sex first and then a first name of that sex from the entry's `from` (rule 5), the candidates' folder and the record of rejections (rule 7). The taste moves into the operator's ADR-071, as ADR-045 §5 rule 4 has a mixed record split: that the surnames are deceased scientists with no weapons work, the owner judging a mixed record; that a language-culture agent takes a surname of its own culture and no persona is a famous person's name; the house style, written by brand-comms. §2, §4 and the Scope say the naming theme and the style are the operator's. The owner's word is the 2026-11-11 answer on the classification (docs/split/move-plan.md §5, ADR-045's Amendments row of that date), decided in docs/split/adr-classification.md.

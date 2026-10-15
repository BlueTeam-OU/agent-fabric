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

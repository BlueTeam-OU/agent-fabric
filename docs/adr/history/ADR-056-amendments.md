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

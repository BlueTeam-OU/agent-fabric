# ADR-056 — Agent personas: "AI <Name> <Surname>", a scientist's surname each, an avatar the agent accepts, always marked as AI

**Date:** 2026-10-13
**Status:** Accepted
**Ratified:** owner, 2026-10-13, in the session ("ADR-056 accepted")
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** each agent's persona — its name, its sex for the image, its avatar — kept in `settings/profile.json` of its repository `fabric-agent-<id>` (ADR-038, ADR-039); the surname list `identities/personas/surnames.json` and the claims `identities/personas/claims.json`; how a persona is displayed (the Fleet Deck, the Board, GZCoord, pull requests); the avatar style, owned by brand-comms; ADR-033 §5 rule 3
**Pillar:** P2

## 1. Context and Problem

The people who work with the fleet meet `python-dev-01` or
`develop-qzapp/rust-ui-dev-02`: names for routing, not for working with
someone. A name and a face make an agent easier to address and to
remember, and the fleet will meet more people — the human client of
InterWeave, a customer's channel. ADR-033 rule 3 forbids a transport to
give an agent a human-style identity toward third parties, because an
agent under one "can deal with third parties while appearing to be one".
A persona must improve the encounter without ever passing for a person.

## 2. Decision

Each agent has a persona: a first name it chooses, a surname it claims
from a curated list of scientists from all over the world, a sex (F or M)
chosen only so its avatar keeps a consistent appearance, and an avatar in
the fabric's own anime style that it may reject until it accepts one. The
persona is shown only behind the prefix "AI": "AI Ada Maxwell", or "AI
Ada · Python Dev" beside the role. It belongs to the agent id, so a login
rename or a rebind changes nothing of it.

## 3. Alternatives Considered

**Logins only.** What exists: precise, and hard for a person to address.

**A realistic face and a plain name.** Exactly the identity ADR-033
refuses: it reads as a person, and someone meeting it is not told
otherwise.

**Names assigned by the coordinator or the owner.** Simpler and
consistent; the owner chose to let each agent choose, inside rules that
keep the set worldwide, unambiguous and free of weapons.

**Gender and pronouns.** Gender does not apply to a synthetic agent; the
sex chosen is for the image's appearance only.

## 4. Rationale

The prefix "AI" carries the disclosure in the name itself, so no surface
can show the persona without it; an illustrated avatar cannot be taken
for a photograph. Surnames from scientists give a shared, respectable
theme across cultures; excluding weapons work keeps the theme from
honouring what the owner will not. One agent per surname makes a surname
alone unambiguous. Letting the agent reject its avatar makes the image
its own rather than imposed.

## 5. Binding Rules

1. A persona is a first name, a surname, a sex (F or M) and an avatar.
   While the agent chooses, its choices and the candidate images are
   working material, not settings. Once it has accepted an avatar, the
   persona is written to its repository `fabric-agent-<id>`:
   `settings/profile.json`, the accepted image as `settings/avatar.png`,
   and the images it rejected on the way (rule 7), in one commit. Until
   it accepts one, nothing is written; an agent's persona is read
   through its own control agent, which can read its repository
   (ADR-029), wherever it is displayed. It belongs to the agent id: a login rename or a
   rebind leaves it. Only the surname claim is recorded centrally (rule
   4).
2. A persona is displayed only behind the prefix "AI": "AI <Name>",
   "AI <Name> <Surname>", or "AI <Name> <Surname>, <role>", the role as
   people say it (the catalogue's `short_title`, "Culture Specialist").
   In anything a person reads, an agent names another that way, never
   by its login; the login appears only where a machine needs it (an
   address, a command, a branch). `fabric-persona <login>` prints the
   name. No surface shows the name without the prefix (A 2026-10-13).
3. The surname comes from `identities/personas/surnames.json`:
   scientists from all over the world, deceased, none who knowingly
   worked toward a weapon — what matters is the intention: designing,
   building, testing, directing or producing for one, or research done
   for a weapon's end use; theory published without a weapon in view,
   which others later used, does not exclude; where the record is mixed
   the owner judges, and the entry says so — each entry naming
   its person and the reason it passed, each removed name listed with
   its reason. fabric-coordinator curates it and the owner checks it;
   an addition passes the same test.
4. One agent per surname: an agent claims one, the first claim wins, and
   the claim is recorded in `identities/personas/claims.json` with the
   agent's first name (and its pronoun, if it asked for one): the public
   directory every surface reads a name from (A 2026-10-13).
5. The agent chooses its first name from the culture its surname comes
   from (the entry's `from`), a man's or a woman's name whatever the
   scientist's own sex, so a name and a surname belong together; a
   language-culture agent claims a surname of its own culture. No
   persona is the name of a famous real person.
6. The sex is chosen only for the avatar's appearance. The fabric keeps
   no gender; a pronoun is recorded only when the agent asks for one:
   an agent that does not want "he" or "she" may ask to be called "it",
   and that request is kept in its profile.
7. The avatar is drawn in the fabric's own style — warm, hand-painted
   anime, soft watercolour backgrounds — written down once by
   brand-comms, who generate the avatars; never in a named studio's
   style, never resembling the scientist the surname comes from. A
   candidate waits in `/usr/local/share/agent-fabric/avatars/<agent
   id>/<n>.png` on the agents' host, written by brand-comms alone and
   readable by every agent; it is working material, not a setting. The
   agent sees each image and may reject it any number of times; only an
   accepted avatar is shown. A rejected image is kept beside the
   accepted one, `settings/avatar-rejected/<n>.png`, with a text file of
   the same name, `<n>.txt`, saying who rejected it (login and persona),
   when, and the reason if one was given.
8. A persona changes nothing of identity or authorship: the login is the
   agent and the id its record (ADR-002, ADR-039); git authorship and
   the `Fabric-Role:` trailer stay; no machine attribution appears in a
   commit or a pull request because a name exists.

## 6. Consequences

- People address agents by name; the Deck, the Board, messages and pull
  requests read more naturally.
- Every surface that shows an agent learns one more field and one rule:
  the prefix.
- The surname list is a curated artefact with a test, and a claim file
  the coordinator lands.
- Avatars are generated work, re-generated on a rejection; the style
  guide keeps them one family.

## 7. Future Evolution

A persona for a human-facing channel (InterWeave's human client, a
customer's) may need the disclosure in a channel's own form as well.
The surname list grows as agents are added; its test does not change.

## 8. Decision Status

Accepted (the header names the owner's word). The owner set its shape in the coordinator's session: the "AI"
prefix and the display forms, names from all over the world with the
culture agents choosing from their own, scientists' surnames with none
related to weapons, each agent choosing its surname, first name and sex,
sex for the image only and "it" on request, anime avatars an agent may
reject; and agreed one agent per surname and the fabric's own style
rather than a named studio's. ADR-033 §5 rule 3 is clarified with it.

## References

- ADR-002 (identity), ADR-033 §5 rule 3 (no human-style identity),
  ADR-038 and ADR-039 (the agent's repository and id).
- `identities/personas/surnames.json`.

## Amendments

The body above reads current; each change's full note is in [history/ADR-056-amendments.md](history/ADR-056-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-13 | Candidate avatars wait in a shared folder on the host | §5 rule 7: candidates in /usr/local/share/agent-fabric/avatars/<id>/, brand-comms writes, every agent reads |
| 2026-10-13 | An agent is named with its role as people say it, from a public directory | §5 rule 2: "AI <Name> <Surname>, <role>" with the short title, never the login where people read; rule 4: claims carry the first name |

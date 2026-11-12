# ADR-071 — This organisation's persona naming theme and house style

**Date:** 2026-11-12
**Status:** Accepted
**Ratified:** owner, 2026-11-11, the answer to the classification's question (docs/split/move-plan.md §5, ADR-045 A 2026-11-11): the records are split, and ADR-056's own ratification, owner, 2026-10-13, in the session ("ADR-056 accepted"), carries to the rules moved here
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** what this organisation's agents' personas are drawn from and how they look: the surname list `identities/personas/surnames.json` and its test of who may be on it, the culture a first name comes from, and the avatar style and the folder candidates wait in; the persona mechanism itself is ADR-056
**Pillar:** P2
**Class:** organisational

## 1. Context and Problem

ADR-056 gave each agent a persona: a surname, a sex for the image, a first name and an avatar, always shown behind the prefix "AI". Three of its rules are not the mechanism but this organisation's choices: that the surnames are deceased scientists none of whom worked toward a weapon, with the owner judging a mixed record, that a first name comes from the surname's culture, and the house style of the avatars, drawn by brand-comms, with the path candidates wait in. Another organisation running the engine would choose its own theme and style. When ADR-056 was split under ADR-045 §5 rule 4 the three rules moved here, their text unchanged but for citations of ADR-056's other rules; ADR-056 keeps the number and rules 1, 2, 4, 6 and 8, and says the naming theme and the style are the operator's.

## 2. Decision

This organisation draws its agents' surnames from scientists from all over the world, deceased and with no weapons work, chooses a first name from the surname's culture, and draws avatars in one house style written down by brand-comms. The rules below are ADR-056's rules 3, 5 and 7, here numbered 1 to 3.

## 3. Alternatives Considered

- **Names assigned by the coordinator or the owner.** Simpler and consistent; the owner chose to let each agent choose, inside rules that keep the set worldwide, unambiguous and free of weapons.
- **A realistic face and a plain name.** Exactly the identity ADR-033 refuses.
- **A named studio's style.** Rejected: the fabric's own style, written down once.

## 4. Rationale

Surnames from scientists give a shared, respectable theme across cultures; excluding weapons work keeps the theme from honouring what the owner will not. A first name from the surname's culture keeps a name, a sex and a surname belonging together. One house style keeps the avatars one family, and an illustrated avatar cannot be taken for a photograph.

## 5. Binding Rules

1. The surname comes from `identities/personas/surnames.json`:
   scientists from all over the world, deceased, none who knowingly
   worked toward a weapon — what matters is the intention: designing,
   building, testing, directing or producing for one, or research done
   for a weapon's end use; theory published without a weapon in view,
   which others later used, does not exclude; where the record is mixed
   the owner judges, and the entry says so — each entry naming
   its person and the reason it passed, each removed name listed with
   its reason. fabric-coordinator curates it and the owner checks it;
   an addition passes the same test.

2. The agent chooses its sex first (ADR-056 §5 rule 6), then its first name: a
   name of that sex, from the culture its surname comes from (the
   entry's `from`), whatever the scientist's own sex, so a name, a sex
   and a surname belong together (A 2026-10-15); a language-culture
   agent claims a surname of its own culture. No persona is the name of
   a famous real person.

3. The avatar is drawn in the fabric's own style — warm, hand-painted
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

## 6. Consequences

- The surname list is a curated artefact with a test; fabric-coordinator curates it and the owner checks it.
- Avatars are generated work, re-generated on a rejection; the style guide (`identities/personas/avatar-style.md`) keeps them one family.

## 7. Future Evolution

The surname list grows as agents are added; its test does not change. Another organisation's engine installation sets its own theme and style in its own record.

## 8. Decision Status

Accepted and in force.

## References

- ADR-056 — the persona mechanism, rules 1, 2, 4, 6 and 8; the record this one was split from.
- ADR-045 §5 rule 4 — a mixed record is split.
- ADR-033 §5 rule 3 (no human-style identity).
- `identities/personas/surnames.json`, `identities/personas/avatar-style.md`.

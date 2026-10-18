# ADR-060 — A holder's addenda specialise a shared role

**Date:** 2026-10-17
**Status:** Accepted
**Ratified:** owner, 2026-10-17, in the coordinator's session ("adr 060 accepted")
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the permanent specialization one agent carries while it holds a shared role: where it is stored (the agent's own store, ADR-038), who writes it, how the launcher reads and renders it into the launch prompt (ADR-002), how it is validated and audited, and how the locale a holder renders in is chosen (ADR-027). Not the shared role's definition, not a project's remit, not working state.
**Pillar:** P1

## 1. Context and Problem

A role is one definition for every holder (ADR-002 rule 9), and a
project's remit says where it applies (ADR-013). Nothing says what one
holder of a role carries that another does not. The three holders of
`legal-expert` answer for different law: Estonia and the Union, Switzerland,
Georgia. Lacking a place for that, the shared charter grew Estonian and EU
rules (its "For `-ee-eu`" paragraph, the directive and direct-effect
clauses), the shared brief grew Swiss and Georgian ones, and the owner sent
each holder an assignment prompt that no later session sees. The same holds
for `language-culture`: its charter carries the English holder's exceptions,
and the only per-holder mechanism, `locale/<suffix>/`, is chosen by the
suffix of the login, which a rename changes (ADR-039), and mixes language
assets with deployment facts (`locale.json` carries a timezone and a search
country, the English one included). The prompt has little room: rendered
for the shortest agent and host names (`x`, `h`), the legal-expert and
language-culture prompts are about 24 700 and 25 700 of `MAX_CHARS`
28 000 characters, more for a real login and host.

## 2. Decision

A holder's specialization of a role is two optional addenda, a
`charter-addendum.md` and a `brief-addendum.md`, and a `holder.json`, kept
in the agent's own store under `settings/roles/<role>/`. The launcher reads
them for the bound role only, from the store's verified committed head, and
renders each addendum after the shared piece it specialises. Only the
agent's parent installs them; an addendum narrows or specialises its role
and never repeals a rule of it. A role whose shared text no longer says
what its holders answer for is marked `holders_specialize: required`, and a
holder of it does not launch without valid addenda.

## 3. Alternatives Considered

- **A `jurisdictions/` (or per-holder) tree under the shared role.** Public,
  keyed by a name the role's taxonomy would have to grow, and it makes a
  holder's specialization part of every holder's definition. Refused: the
  specialization belongs to the holder, not to the role.
- **`identities/agents/<login>.json`.** Descriptive only by its own README,
  and keyed by the login. Refused.
- **The project remit.** It follows the working copy and arrives at session
  start; a jurisdiction does not change with `cd`. Refused.
- **A copy of the whole charter per holder.** Every shared change would
  have to be made N times. Refused: an addendum is a delta.
- **The agent writes its own addenda.** ADR-038 rule 3 lets an agent write
  its store. Refused for this path: an agent would rewrite its own
  permanent instructions without review.
- **Degrade silently when addenda are missing.** Right for most roles,
  wrong for one whose shared text no longer names a jurisdiction: the holder
  would launch not knowing what law it answers for. Hence the per-role flag.

## 4. Rationale

The store is already the agent's private, signed, per-id repository for
settings (ADR-038, ADR-039, ADR-042, ADR-056), so the specialization follows
the agent through a rename and never enters the public tree. Reading from
the committed head, not the working tree, and checking the signer of the
last commit that changed the path over the whole history, makes the rendered text the text the parent
installed, and reading each file from that commit's own tree, each blob
checked against its object name, makes it the text the parent installed. Separating `holder.json` (who this holder is: its locale, its
deployment) from `locale/<lang>/` (what a language needs) removes the
login-suffix key while moving only the role-independent prompt pieces,
once per language.

## 5. Binding Rules

1. A holder's specialization of role R is `settings/roles/R/` in the
   agent's store `fabric-agent-<id>`: `charter-addendum.md`,
   `brief-addendum.md` and `holder.json`, each optional, no other file,
   no link, no subdirectory, except an English gloss beside an addendum in
   another language (rule 9). It holds no working state: no job, task,
   plan, note or project fact.
2. The launcher reads only the directory of the bound role, from the
   store's committed `HEAD`, never the working tree, never `env/`, and
   decrypts nothing. It refuses a store whose `.agent-id` is not the id
   lineage gives the running login, or whose `HEAD` does not descend from
   its trusted base (ADR-042).
3. The last commit that touched `settings/roles/R/` is signed by the
   agent's parent, "last" judged over the whole history and not along
   the line git's log simplification follows: a merge whose version of
   the directory is not one its parents carry over is itself the change
   (A 2026-10-18); the launcher verifies it with the parent's public key
   alone and refuses any other signer, the agent's own included. The
   record of an install is its signed commit's tree: the launcher renders
   the files of `settings/roles/R/` as the tree of that last parent-signed
   commit holds them, each blob checked against its object name, which is
   the tree at `HEAD` on that path: an edit committed after the
   install, by anyone, is refused, not rendered under the parent's
   signature.
   `settings-put` refuses paths under `settings/roles/`; the parent
   installs with a command of its own, in one signed commit naming the
   author, each review pass with the digest of the text it read, the
   owner's approval, and the shared digests the addenda were written
   against.
4. The prompt is: header, shared charter, charter addendum, shared brief
   (or brief-missing), brief addendum, team, memory. With no addenda it is
   byte-for-byte today's prompt, except where rule 8 itself moves a
   holder's locale pieces.
5. An addendum specialises or narrows its role: it may add scope, method
   and boundaries for its holder, and never repeals, overrides or
   contradicts a rule of the shared charter, brief or another role's
   authority. Lint cannot see that; the review that precedes the install
   does, and the install commit records it.
6. Each addendum is at most 4 000 characters; the render ceiling is the
   shared ceiling plus the addenda. Its frontmatter names its `class`
   (`charter-addendum` or `brief-addendum`), `role`, `agent_id`, `lang` and
   `against_digest`, the body digest of the shared piece it was written
   against; a lag is a warning, never a refused launch. `lang` is the
   text's language as BCP-47 spells it (`ka`, `ru`, `en`); the review
   passes rule 9 wants are by `language-culture-<key>`, the holder of the
   locale whose `locale/<key>/locale.json` tag has that language (`ka-GE`,
   so `language-culture-ge`) (A 2026-10-18).
7. A role is `holders_specialize: optional` unless the catalogue says
   `required`. For an optional role, a store with no addenda renders
   today's prompt; for a required role it is a refused launch. For either,
   an addendum that is invalid or unverifiable refuses the launch: tamper
   is never read as absence.
8. `holder.json` names the holder's `locale` and its deployment facts
   (timezone, search country). The launcher chooses `locale/<locale>/`
   from it, and the login's suffix only while a holder has no
   `holder.json`. `locale/<lang>/` keeps what a language needs: its
   translations, its `locale-worker`, its dictionaries and its language
   tags. The translations of the role-independent prompt pieces (header,
   team, memory, brief-missing) live once per language in
   `identities/prompt/locale/<lang>/`, for every role, authored by
   `language-culture-<lang>`; a role's own `locale/<lang>/` carries its
   charter and brief. A holder whose locale is not English renders none of
   the fabric's prompt in English: a missing rendering it would need is a
   lint finding.
9. An addendum in a locale is authored by the holder in that language and
   reviewed by `language-culture-<locale>` in the two passes of ADR-027 §5
   rule 3 before the parent installs it; a change that may alter what the
   holder answers for goes back to the holder, never in by the reviewer.
   It carries an English gloss, `<name>.gloss.en.md`, written by the holder,
   with `glosses_digest` the body digest of the text it glosses; the gloss
   is never rendered, a stale gloss refuses the install, and the reviewer's
   second pass reads it against the text.
10. The launch records the store commit it read and the commit of the
    addenda (`AGENT_FABRIC_LAUNCH_STORE_SHA`,
    `AGENT_FABRIC_LAUNCH_ADDENDA_COMMIT`); `fabric-status` reports them and
    says when the store has moved past the launch. A holder's change moves
    that holder's prompt digest and no other's.
11. A rebind leaves the old role's addenda stored and unread; a rebind back
    reads them again. A rename changes nothing: the key is the agent id.
    Retiring an addendum is a parent-signed deletion.

## 6. Consequences

- The shared `legal-expert` charter and brief become jurisdiction-free; the
  Estonian and EU, Swiss and Georgian material moves to its holders'
  addenda, and `locale/ge/` re-renders the universal text. The
  `language-culture` charter loses the English holder's paragraph to that
  holder's addendum.
- legal-expert-ge's header, team and memory renderings and
  language-culture-ge's differ in terms on purpose (a lawyer's reading of
  some words). When rule 8 moves those pieces to
  `identities/prompt/locale/ge/`, language-culture-ge reconciles them into
  one text both holders' reviews accept, in the two passes; until then a
  role's own rendering wins over the shared one.
- The parent becomes the one installer of every holder's specialization:
  more work for fabric-coordinator, and one place where it is reviewed.
- An agent owns its home, the store's `.git/config` included: rules 2 and
  3 stop an accident and a casual self-edit, not a determined agent, as
  the fabric's other guards do.
- A holder's private specialization is not in the public tree: its review
  reads it from the parent's mirror, and its English gloss is what the
  owner audits.

## 7. Future Evolution

Reopened if a specialization needs to be shared by several holders (a
second Swiss holder), which would argue for a public layer again; or when
the per-holder locale fallback (rule 8) has no remaining user and can go.

## 8. Decision Status

Accepted. Rules 1-7 and 9-11 bind with the mechanism; rule 8 (the locale
chosen by `holder.json`) binds with its stage. The amendments it implies
are made where the behaviour lands: ADR-002, ADR-038 and ADR-042 with the
mechanism, the rest with rule 8's stage:
ADR-002 rules 4, 8, 9; ADR-018 §5 rule 5 (the carve-out admits
`language-culture-<lang>` to `identities/prompt/locale/<lang>/`); ADR-027
rules 1, 6, 9, 11 and 13 (the locale named by `holder.json`, the worker and
the search setup keyed on it, the shared prompt pieces per language, no
English piece for a non-English holder); ADR-038 rule 3; ADR-042 rule 2.
ADR-057 §5 rule 5 needs none: its checker judges a commit from public
data alone (the keys, the lineage, the committed holders and locale
directories), and a holder's `holder.json` is private, so a locale signer
stays named by its login's suffix or its committed holding (A 2026-10-18).

## References

- ADR-002, ADR-013, ADR-027, ADR-038, ADR-039, ADR-042, ADR-056.
- `tools/fabric/launch_prompt.py`, `tools/fabric/secretstore/trust.py`,
  `tools/fabric/secretstore/settings.py`, `identities/roles/catalog.json`.

## Amendments

The body above reads current; each change's full note is in [history/ADR-060-amendments.md](history/ADR-060-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-17 | Accepted; the digest check is per file; sizes restated | Status Accepted; §5 rule 3's record of an install is its signed commit's tree; §4 names the digest check; §1's size restated; §8 says which amendments land with which stage |
| 2026-10-18 | ADR-057 needs no amendment; what `lang` names | §8: the signature checker reads public data only, so a holder's private locale cannot name a signer; the stage's other amendments (ADR-018, ADR-027) are made. §5 rule 6: an addendum's `lang` is its BCP-47 language (`ka`); its reviewer is the holder of the locale whose tag has that language (`language-culture-ge`) |
| 2026-10-18 | The last commit on the path, over the whole history | §5 rule 3, §4: a merge whose version of the directory its parents do not carry over is the change, so a merge cannot route the path to an older install |

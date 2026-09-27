# ADR-028 — The house i18n standard; GZCoord speaks the reader's language

**Date:** 2026-09-21
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #53 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** communication/gzcoord/i18n/ (README.md — the manual, en-US.json, i18n.schema.json); communication/gzcoord/scripts/i18n.mjs and its callers gzmsg.mjs, send.mjs and inbox.mjs; communication/gzcoord/tests/i18n.test.mjs; an active locale's dictionary under identities/roles/<role>/locale/<suffix>/; the dictionary checks in tools/fabric/lint.py; `GZCOORD_DEFAULT_LOCALE_ONLY` in tests/run.sh; any dictionary the fabric adds later
**Pillar:** P4

## 1. Context and Problem

ADR-027 moved every English the fabric controls out of a
language-culture holder's session — its prompt, its worker, its search,
its memory. One English surface was left and named as residue: the
inbox. Every drain and every delivery printed the fabric's own lines —
the head line, the delivery title, the validator's diagnostics, the cut
notice, the watch's transport lines, every error — in English, into the
session of a holder whose rule is to reason in its locale.

The inbox is two things. The message is the wire: its sender wrote it,
and other agents match its metadata keys and type names by name. The
lines around it are the fabric's own text, written for whoever reads
them. The first cut of the change translated only the `INVALID:` and
`warning:` prefixes of the validator's diagnostics and left their
substance English, while a comment in the module said they were
covered.

The managed projects already had a way to keep dictionaries, recorded as
gzapp's ADR-024 (localization as a first-class contract) and used by the
projects' own locale files. A second shape, invented for one tool, would
be one more thing every holder has to learn.

## 2. Decision

**Any dictionary the fabric keeps follows the house i18n standard**: one
flat key → string JSON file per locale, named for the locale's BCP-47 tag
(`en-US.json`, `ru-RU.json`); keys are flat dotted slugs
(`inbox.head`, `watch.relay-back`); values are non-empty strings with
`{name}` interpolation; `en-US` is mandatory; every active locale is
complete against it. `communication/gzcoord/i18n/README.md` is the manual
and cites where the house keeps the standard.

**The GZCoord tools speak the reader's language.** Every line the tools
print around a message goes through one seam,
`communication/gzcoord/scripts/i18n.mjs`, in the language of the login
that runs them. The seam is inside the validator, not at the inbox's
edge: `validate()`'s diagnostics are dictionary keys, so a refusal a
holder reads from `send.mjs` or the `gzmsg` CLI while composing is in its
language too. The message itself — its body, the metadata keys, the type
names and `broadcast` — is never translated.

A login's dictionary is found the way the launcher finds its prompt: the
login's suffix under the role it is bound to, and that locale
directory's `locale.json` for the tag. The dictionary lives with that
locale's other translations, `identities/roles/<role>/locale/<suffix>/<tag>.json`,
where its holder can commit it (ADR-018's carve-out) — not beside
`en-US.json`.

Today one locale is active: `ru` (`ru-RU.json`, the same 123 keys as
`en-US.json`). The `ge` locale has no `ka-GE.json`, so its holder reads
the default locale.

## 3. Alternatives Considered

- **Translate the inbox's output whole, message included.** Rejected: a
  translated metadata key or type name names nothing; readers match them
  across locales. The message is its sender's.
- **Translate at the inbox's edge only.** Rejected: the validator's
  sentences are printed by three tools, and the first cut showed an edge
  translation leaves the substance English.
- **All dictionaries beside `en-US.json`**, as the house layout has
  them. Rejected for the fabric: a translation has no author but its
  holder, and the fence that makes that true is a path rule; a
  dictionary in a shared directory is a file its own author cannot
  commit.
- **A tool-specific format** (a JavaScript module of strings, gettext).
  Rejected: the house already has a standard, and its projects' holders
  already review files of that shape.

## 4. Rationale

The line ADR-027 draws for the prompt — prose is free to translate,
identifiers are the whole risk — is the same one drawn here inside a JSON
value: lint holds every identifier in a translated value to the count in
`en-US.json`. Reusing the house standard means a holder reviews one
shape everywhere, and the fabric's lint enforces the one property the
standard cares most about — completeness — before a file lands.

**Where the fabric's copy departs from the standard, and why.** gzapp's
ADR-024 forbids a client's key-level fallback (§5 rule 14) and treats a
missing key at runtime as fatal: completeness is guaranteed at
publication. The GZCoord tools run at every session start, and a session
start never fails on a translation, so `i18n.mjs` overlays an active
dictionary on the default one: a key the dictionary lacks prints its
`en-US` line, and an unreadable dictionary leaves `en-US` standing whole.
Nothing is invented — every line printed is an authored line — but a
missing key *is* a key-level fallback the standard does not allow its
clients. The fabric keeps the standard's guarantee where it can be kept:
`tools/fabric/lint.py` refuses an active dictionary with a key missing or
extra against `en-US.json`, so the runtime fallback is reached only by a
dictionary lint would not have let land.

## 5. Binding Rules

1. A dictionary the fabric keeps is one flat key → string JSON file per
   locale, named `<BCP-47 tag>.json`; keys match
   `communication/gzcoord/i18n/i18n.schema.json`'s pattern (dotted slugs);
   values are non-empty strings with `{name}` interpolation; `en-US.json`
   is mandatory and is the default. Before a new fabric surface gets
   dictionaries, the managed projects' locale files are read, not a new
   format invented.
2. A locale is active when its `<tag>.json` exists. An active locale's
   dictionary lives at `identities/roles/<role>/locale/<suffix>/<tag>.json`;
   only the default lives in `communication/gzcoord/i18n/`.
3. `tools/fabric/lint.py` refuses an active dictionary whose key set
   differs from `en-US.json`'s in either direction, a key that is not a
   dotted slug, an empty or non-string value, a control character, a
   value that loses a protected identifier its `en-US` line carries, and
   a dictionary no value of which is in the locale's script.
4. Every line a GZCoord tool prints around a message goes through
   `i18n.mjs`, the validator's diagnostics included. The message body,
   the metadata keys (`FROM`, `TO`, `TO-ROLE`, `MESSAGE-ID` and the
   rest), the type names and `broadcast` are never dictionary values.
5. A login reads the dictionary named by `locale.json`'s `tag` in
   `identities/roles/<bound role>/locale/<login suffix>/`; with no bound
   role, no locale directory, no tag, the tag `en-US`, or no `<tag>.json`,
   it reads `en-US`. A key the active dictionary lacks, or an unreadable
   dictionary, falls back to `en-US`; a key missing from `en-US.json`
   prints as its own name. No line is ever invented.
6. A locale's `locale.json` may carry a `reminder`, the standing line its
   holder reads; the inbox appends it to the head line and nowhere else.
   It is not a dictionary key.
7. `GZCOORD_DEFAULT_LOCALE_ONLY=1` — exactly `1` — pins the default
   locale for the login running the tools and silences the reminder,
   saying so once on stderr when it suppresses a locale directory.
   `tests/run.sh` exports it; a suite asserting a tool's output runs
   under it.
8. A new or removed key reaches every active `<tag>.json` in the same
   change, the holder's through that holder. A changed `en-US` value is
   announced to each locale's holder; nothing detects the staleness.
9. The coordinator commits `en-US.json`, the machinery, the lint and the
   tests, and authors no translation.

## 6. Consequences

- A default-locale login's output is byte-identical to what it was before
  a dictionary existed (`communication/gzcoord/tests/i18n.test.mjs`'s
  load-bearing case).
- A tool's output depends on who runs it. A suite that pins English is
  green in CI, which has no locale, and red on a holder's login; rule 7
  is the answer.
- Adding a key costs a change on every active locale, which only its
  holder can make: an English change that adds a key cannot land with a
  green lint until each active locale's holder has translated it. With one
  active locale this is one holder's commit.
- The standard is the managed projects' where they keep dictionaries:
  gzapp's `product/i18n/<tag>.json` and each gzapp.decks deck's
  `i18n/<tag>.json` are flat files of this shape. Not every project keeps
  dictionaries: the gzapi.ge site holds its two languages in a
  TypeScript content module (`src/i18n/content.ts`). The fabric follows
  the standard; it does not audit the projects against it.

## 7. Future Evolution

A `ka-GE.json` from the `ge` holder makes `ge` the second active locale.
A plural form, if a tool line ever needs one, is taken from how the
managed projects already spell it, by amendment. Detecting a stale
translation of a changed value — which rule 8 leaves to a message — would
need a digest per value, as the prompt translations carry per file.

## 8. Decision Status

Accepted. The fabric's dictionaries follow the standard, and the GZCoord
tools print the reader's language; `ru` is the one active locale.

## References

- `communication/gzcoord/i18n/README.md` (the manual), `en-US.json`,
  `i18n.schema.json`.
- `communication/gzcoord/scripts/i18n.mjs`, `gzmsg.mjs` (`validate`),
  `send.mjs`, `inbox.mjs`; `communication/gzcoord/tests/i18n.test.mjs`.
- `identities/roles/language-culture/locale/ru/ru-RU.json`, `locale.json`.
- `tools/fabric/lint.py` (`i18n_default_dictionary_findings`,
  `i18n_dictionary_findings`); `tests/run.sh`.
- gzapp's ADR-024 (localization as a first-class contract): the house
  standard, its §2.5 fallback rules and §5 rule 14.
- ADR-018 (the locale carve-out), ADR-027 (the bridge; what is
  translated for a holder and what is named as residue).

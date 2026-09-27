# The GZCoord tools' dictionaries

Decisions: agent-fabric ADR-028 (`docs/adr/ADR-028-house-i18n-standard-gzcoord-speaks-the-readers-language.md`).

Every line the inbox prints **around** a message, in the language of the
login that reads it. The message itself is the wire and is never
translated.

This follows the house i18n standard — gzapp's ADR-024, whose own
statement of it is `product/i18n/README.md` and
`contracts/i18n/i18n.schema.json` in that repository. What that standard
fixes, and this directory keeps:

- **One flat JSON dictionary per locale**, `<tag>.json`, named for the
  locale's BCP-47 tag (`en-US`, `ka-GE`, `ru-RU`). A locale is *active*
  when its file exists.
- **Keys are flat dotted slugs**, `<area>.<thing>` — `inbox.head`,
  `replay.no-message`, `watch.relay-back`. Case-sensitive, kebab inside
  a segment.
- **Values are non-empty strings** with `{name}` interpolation.
- **Key completeness across active locales**: a key in one dictionary
  and not in another blocks the change. `tools/fabric/lint.py` is where
  that is enforced here.
- **`en-US` is mandatory** — the default every fallback lands on.

## Layout

```text
communication/gzcoord/i18n/
├── README.md
├── i18n.schema.json         the shape, this repository's copy
└── en-US.json               the default locale
```

An active locale's own dictionary is **not** beside `en-US.json`. It
lives with the rest of that locale's translations:

```text
identities/roles/<role>/locale/<suffix>/<tag>.json
identities/roles/language-culture/locale/ru/ru-RU.json
```

That is not a departure taken for taste. A translation is authored by
the holder of the role named for that locale and by nobody else, and the
authority fence that makes this true is a path rule: a commit staging
nothing but `identities/roles/<role>/locale/<suffix>/` passes as that
holder's (`policies/AUTHORITY.md`, `policies/githooks/locale-carve-out.sh`).
A dictionary in a shared directory would be a file its own author could
not commit. The standard's own layout already separates the contract
from the dictionaries; this separates them one step further, for the
fence.

## Which dictionary a login reads

By the **login's suffix**, the launcher's rule — `language-culture-ge`
ends in `-ge`, so the locale directory is `locale/ge/` — and that
directory's `locale.json` names the tag:

```json
{ "tag": "ka-GE", "timezone": "Asia/Tbilisi", ... }
```

`ge` is Georgian, not German; the tag is data for exactly that reason.
No role bound, no locale directory, no `tag`, no `<tag>.json`: the
default locale, and the session starts either way.

**One departure from the standard.** A key an active dictionary lacks
prints its `en-US` line, and an unreadable dictionary leaves `en-US`
standing whole. Nothing is invented, but the first is a key-level
fallback, which gzapp's ADR-024 does not allow its clients. The tools
run at every session start and a session start never fails on a
translation; the standard's guarantee is kept before the file lands
instead — lint refuses an active dictionary that is not complete.

## Running the tools in the default locale

The tools speak the **reader's** language, so what they print depends on
which login runs them. That is the point, and it is a trap for anything
that asserts their output: a suite pinning English is green on a login
with no locale directory and red on every holder's — the worst way round,
because CI has no locale and so never says.

`GZCOORD_DEFAULT_LOCALE_ONLY=1` in the environment pins the default
locale whatever the login is. `tests/run.sh` exports it; use it to
reproduce a holder's report in a language you can read.

**Exactly `1`.** Any other value — `0`, `false`, `no`, unset — leaves the
login's own locale standing. Truthiness would have made `=0` mean yes,
which is the one reading an operator setting it that way cannot have
intended.

**It says so when it suppresses something.** With the switch on and a
locale directory present for that login, one line goes to stderr naming
the directory it is not reading. A holder served English, without its
standing reminder, should not have to guess whether its dictionary is
missing or merely pinned away.

It governs the **ambient** resolution only — what a tool picks for the
login running it. A caller that names a locale (`dictionary(me, { root,
env: {} })`) is asking for that one and gets it, because it asked.

## What is never a key

The wire's vocabulary: the message body as its sender wrote it, the
metadata keys (`FROM`, `TO`, `TO-ROLE`, `MESSAGE-ID`), the message type
names and `broadcast`. A reader matches those by name across locales; a
translated one would name nothing. `SPEC §17`, paths, flags, model ids
and `GZCOORD/1` are identifiers *inside* a value — lint holds every
dictionary to the same count of them as `en-US.json`.

## Changing a line

1. Edit `en-US.json`.
2. Every active locale must carry the same key set, so a **new or
   removed** key reaches every `<tag>.json` in the same change — a
   holder's, through that holder.
3. A **changed value** leaves the translations complete but stale.
   Nothing detects that for you: say so to each locale's holder, the way
   the standard's propagation checklist does.
4. `tests/run.sh`.

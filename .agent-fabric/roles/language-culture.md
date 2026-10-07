---
role: language-culture
class: remit
project: agent-fabric
description: "What language-culture covers in agent-fabric: each locale's translations of the fabric's prompts and tools, kept aligned across locales."
origin:
  - agent: user
    host: develop-qzapp
---

# language-culture — remit in agent-fabric

The charter is the function; this is what it covers in the control
plane's own repository. Each holder of the role holds one locale, named
by the login's suffix (`-ge` Georgian, `ka-GE`; `-ru` Russian, `ru-RU`).

**Yours here.** Your locale's directory,
`identities/roles/language-culture/locale/<suffix>/`: the translated
prompt pieces (charter, brief, header, team, memory, harness, worker),
`locale.json`, and the GZCoord tools' dictionary `<tag>.json`, which
holds every key of `communication/gzcoord/i18n/en-US.json` and no
other. You commit it on your own `for/user/<what>` branch; fabric-
coordinator folds and merges it (agent-fabric `CLAUDE.md`, the locale
carve-out). Every other path is read-only for you.

**Locales stay aligned** (the owner, 2026-10-07). Every locale carries
every artifact any other locale has: when one locale gains a
translation, the others gain it in the same round, and fabric-
coordinator asks every holder together. When the English source of a
piece you translate changes, its translation is re-rendered against the
new source; lint names a locale whose files or keys have fallen behind,
and a red lint is fixed by landing the missing translation, never by
dropping the check.

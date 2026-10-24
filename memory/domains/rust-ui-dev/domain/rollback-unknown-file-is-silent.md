---
role: "rust-ui-dev"
class: domain
topic: "rollback-unknown-file-is-silent"
description: "Downgrade safety for a client's local profile/store: a strict parser refuses a newer version of a file it knows but silently ignores a file it never heard of; a format marker is what closes it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 8cb2da1e2568f62b
---

## Downgrade safety for a client's local profile/store: a strict parser refuses a newer version of a file it knows but silently ignores a file it never heard of; a format marker is what closes it

Version checks (`deny_unknown_fields`, SQLite `user_version`, a config `schema_version`) protect
a rollback only for files the older build already knows. A file a newer build *added* is
invisible to the older one: it starts, serves, and acts as if the setting never existed. For a
security setting that is a silent reversal (InterWeave, measured 2026-10-20: an older daemon on
a newer profile re-enabled a disabled endpoint and re-allowed a revoked peer, nothing shown).

**How to apply** when a change adds a persisted artefact to a client's profile or store:
- ask what the previous build does with the new file, and measure it with a real older binary
  if the project has one, not by reading;
- downgrade protection is a profile-level format number every loader checks and refuses when it
  is above its own, naming the file and both numbers, writing nothing; it is raised only by the
  component that writes the profile, never lowered, and a change adding an artefact an older
  build would ignore bumps it in that change;
- the marker lives with what the build writes, never in a file the person authors (a build
  never rewrites that, so it cannot raise the number there);
- builds older than the marker stay unprotected: say so in the release text, and tell the person
  "roll forward, never back past the newest release you used", not "older releases refuse".

InterWeave's instance: [[profile-format-marker]], ADR-0028 A 2026-10-20.

*References: profile-format-marker*

*Observed 2026-10-23 (rust-ui-dev)*

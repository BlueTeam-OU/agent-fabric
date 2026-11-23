---
role: "flutter-dev"
class: domain
description: "Dart null-aware map-entry operator binds to the value, not the key"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-74e1ddd4096a45ce"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 0b58eb6edf5a8367
  - 1866c560b204b175
  - b195c9e597a9d99b
  - c3f058aea68e8c2f
  - e9dd63a03944ae34
---

## Dart null-aware map-entry operator binds to the value, not the key

Dart's null-aware map-entry syntax is `'key': ?value` — the `?` belongs on the value side. The analyzer's `use_null_aware_elements` hint can be satisfied by putting `?` on the key instead (`?'key': value`), which looks plausible but is rejected outright ("key can't be null"). This has been hit more than once while adding conditional JSON-serialization entries.

## Uri.resolve() corrupts URL templates; absolute-URI detection needs a scheme regex, not an http prefix check

`Uri.resolve()` percent-encodes literal `{`/`}` characters, so it cannot be used to resolve a URL template containing placeholders like `{z}/{x}/{y}` against a base URL — it silently mangles the template. String splicing is required instead. When splicing, "is this reference already absolute" must be tested with a general URI-scheme regex (`^[a-zA-Z][a-zA-Z0-9+.-]*:`), not an `http://`/`https://`-only prefix check: a self-hosted tile server can emit internal schemes (e.g. `mbtiles://`) in style documents, and splicing those onto a relative base path instead of passing them through unchanged turns an honest upstream problem into a silent, misleadingly-named 404 on the client.

---
role: "db-admin"
class: domain
topic: "pg-regex-s-admits-nbsp"
description: "Postgres 18's regex \\S admits U+00A0 and follows the DB ctype; spell an ASCII range for a \"no whitespace\" CHECK"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - bd916f7a6d791e69
---

## Postgres 18's regex \S admits U+00A0 and follows the DB ctype; spell an ASCII range for a "no whitespace" CHECK

On postgres:18-alpine (18.6), `U&'ka\00A0GE' ~ '^\S+$'` is TRUE: `\S`
is `[^[:space:]]`, ctype-dependent, and does not count NBSP as space.
A CHECK meant to refuse "blank or whitespace" written with `\S` lets
NBSP through, and what it admits can differ between the test and prod
databases. For a value that is ASCII by definition (a BCP-47 tag, RFC
5646 §2.1), spell the range: `'^[!-~]+$'`. That is printable ASCII
without the space, compared by code point, and the same under every
locale. Probed with a throwaway container before review (0027
journeys.reader_locale, j45, 2026-10-30). Same family as [[btrim-is-not-dotnet-trim]].

*References: btrim-is-not-dotnet-trim*

*Observed 2026-10-30 (db-admin)*

---
role: "db-admin"
class: domain
topic: "btrim-is-not-dotnet-trim"
description: "A blank or leading-digit test written in SQL and again in .NET disagrees on whitespace: btrim's default strips U+0020 only, Trim()/IsNullOrWhiteSpace strip 25 code points, [[:space:]] depends on the ctype."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 114c87ce73d49243
---

## A blank or leading-digit test written in SQL and again in .NET disagrees on whitespace: btrim's default strips U+0020 only, Trim()/IsNullOrWhiteSpace strip 25 code points, [[:space:]] depends on the ctype.

Whitespace means different things on the two sides of the database:

- Postgres `btrim(x)` with no second argument strips U+0020 and nothing else.
  So `btrim(x) <> ''` lets through a value made only of NBSP (U+00A0), a tab,
  U+3000 or U+202F.
- .NET `string.Trim()` and `IsNullOrWhiteSpace` use `char.IsWhiteSpace`,
  which is 25 code points in .NET Core. U+180E is not one of them: it was
  whitespace in .NET Framework and stopped being whitespace in .NET Core 3.0,
  so a list copied from the old documentation carries one code point too many.
- A `[[:space:]]` class or `\s` depends on the database's ctype/locale. It can
  pass in CI and behave differently on a database with another locale.

What went wrong in the places wave (gzapp #844, 2026-09-17): the export
computed a value in SQL over `btrim`, and the importer computed it again in C#
over `.Trim()` and refused any disagreement. A house number that starts with
NBSP got NULL from one side and 12 from the other, and the whole dataset
failed to import. The first fix (539acb81) dropped the trim on the SQL side.
That fixed the overflow case and broke a leading ASCII space, which had
worked before. The settled fix was one CTE, `ws(chars)`, that spells out
`char.IsWhiteSpace` code point by code point
(infra/local/nominatim/export-places.sql). I checked it against a generated
.NET Core list by diffing the two sets, not by reading them.

**Why:** this disagreement throws no error. The value just comes out
different on each side, and in an import that runs as one transaction it
takes the whole file down with it.

**How to apply:** for a "not blank" CHECK or a SQL rule that a .NET reader
also applies, either pass the explicit character set as btrim's second
argument or leave the rule to one side only. Test it with NBSP, a tab and
U+3000, not just a space. When the two sides must agree, test them on the
same inputs in a container ([[verify-the-mutation-fired]]).

*References: :space:, verify-the-mutation-fired*

*Observed 2026-10-15 (db-admin)*

---
role: "backend-dev"
class: domain
description: "Two nullable-reference-type gotchas in test doubles/assertions against framework interfaces"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-74e1ddd4096a45ce"
    host: "develop-qzapp"
  - clone_id: "clone-8a543ee5423d427c"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 1f24fdb011d492bb
  - 2a7303a857962944
  - 2af7104573e16cc0
  - 61b1889222fa30ef
  - b2fa9b84c2004fc6
---

## Two nullable-reference-type gotchas in test doubles/assertions against framework interfaces

Two recurring C# nullable-reference-type gotchas surfaced while writing test doubles/assertions against framework interfaces. First: a hand-written `IDbConnection` stub declaring `public string ConnectionString { get; set; }` triggers CS8767, because the real interface's setter accepts `string?` — the fix is `[AllowNull]` on the property, not widening the property's own type to nullable (which would ripple non-nullability assumptions elsewhere in the stub). Second: `Assert.Equal(actual, ['Origin', 'Accept-Encoding'])` using a C# collection-expression literal against a `StringValues.ToArray()` value fails to compile with CS8631, because collection-expression type inference picks `string?[]` while xUnit's `Assert.Equal<T>(ReadOnlySpan<T>, T[])` overload wants a non-nullable `T[]` — an explicit `new[] { ... }` plus a null-forgiving `!` on the actual value resolves it where a collection expression won't.

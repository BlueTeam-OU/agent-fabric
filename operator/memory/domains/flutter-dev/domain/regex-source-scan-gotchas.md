---
role: "flutter-dev"
class: domain
description: "A quote-exclusion character class breaks on delimiter-swapped literals; use a tempered token, require unicode:true for \\p{L}, and scan whole files for multi-line matches"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-09-05"
origin:
  - clone_id: "clone-74e1ddd4096a45ce"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 232234094091c321
  - 5da2b54c95292288
  - 77efb35641e4c28b
  - 8c3e77864f92f0ec
  - a7a9ad40a597b457
  - d58b066fb12673e0
  - f9fc332b0400c4b9
  - ff17e678428003a8
---

## A quote-exclusion character class breaks on delimiter-swapped literals; use a tempered token, require unicode:true for \p{L}, and scan whole files for multi-line matches

Three regex/Dart-source-scanning traps surfaced repeatedly while hardening a hand-written hardcoded-text scanner (the project's localisation contract forbids literal UI text), and all three generalize beyond that one file. First: to match the content of a quote-delimited string literal, a character class excluding both quote types (`[^'"\n]{2,}`) looks safe but is wrong — it also excludes the *other* quote character even where that one is legitimate content, so `Text("Don't continue")` fails to match because the apostrophe is treated as a terminator, and the literal silently escapes any guard built on that pattern. The fix is a delimiter-aware 'tempered token', `(?:(?!\1)[^\n])`, backreferencing whichever quote actually opened the string — it excludes only that character, letting the opposite quote type through as content. Second: Dart's `\p{L}` Unicode-letter-class escape requires the `RegExp` to be constructed with `unicode: true`; there is no error if you use plain ASCII `[A-Za-z]` instead, it just silently matches zero letters for any non-Latin script (Georgian, Cyrillic, etc.) — exactly the failure a script-completeness check exists to catch. Third: a source-scanning regex test built on `File.readAsLinesSync()` plus per-line matching will systematically miss any construct `dart format` splits across lines (its default output for any argument that doesn't fit on one line, e.g. `Text(\n  'Copy',\n)`) — a reliable scanner must `readAsStringSync()` the whole file and derive reported line numbers from each match's character offset, never from a line-loop index.

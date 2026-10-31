---
role: "edge-hosting"
class: domain
topic: "node-to-python-port-parity-traps"
description: Where a Python port of a Node script silently differs from it (regex, whitespace, paths, decoding, file names, locale) — check these before claiming parity
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fb101c7feb319538
---

## Where a Python port of a Node script silently differs from it (regex, whitespace, paths, decoding, file names, locale) — check these before claiming parity

Found porting blueteam.ee `deploy/check-dist.mjs` to `deploy/check_dist.py`
(blueteam.ee #15, 2026-10-19, five review rounds), each held to the Node script
as oracle:

- JS `\s` and `trim()` are ECMAScript's set (includes U+FEFF, excludes
  \x1c-\x1f); Python's `\s`/`strip()` differ both ways. Spell the class out.
- JS `/i` without `u` folds ASCII only; Python `re.I` matches U+017F as `s`,
  U+212A as `k`. Use `re.I | re.A`.
- JS `.` stops at \n, \r, U+2028, U+2029; Python's only at \n. JS `$` without
  `m` is Python `\Z`.
- `decodeURIComponent` throws on a bad `%` or invalid UTF-8; `urllib.parse.unquote`
  never throws. Check escapes, then `unquote_to_bytes(...).decode("utf-8")` strict.
- Node `path.join` concatenates then normalises; `os.path.join` drops everything
  before an absolute part. Use `normpath("/".join(parts))`.
- `readdirSync` is byte-sorted (libuv); `os.listdir` is not: `sorted()`.
- File names: Node decodes non-UTF-8 names with U+FFFD (then usually fails to
  stat them); Python keeps surrogate escapes and succeeds — a fail-open on a
  gate. Python also follows the locale (Latin-1 changes matches): re-exec in
  `-X utf8` mode and refuse non-UTF-8 names.
- A recursive walk hits Python's recursion limit (~1000 levels) where Node
  did not; `pathlib.mkdir(parents=True)` recurses too.
- Test harness: `subprocess.run(text=True)` turns \r into \n — capture bytes.

**How to apply:** a frozen contract states the mechanism ("as Node's UTF-8
decoder replaces them"), never a count or rule you have not measured; two
review rounds went to rewording one such parenthetical.

*Observed 2026-10-19 (edge-hosting)*

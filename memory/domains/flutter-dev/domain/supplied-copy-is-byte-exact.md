---
role: "flutter-dev"
class: domain
topic: "supplied-copy-is-byte-exact"
description: "Locale copy can carry bytes an eye cannot check — a Cyrillic С that looks like Latin C, a no-break space before a unit or after № — so commit supplied strings by paste and verify the code points with a script."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 21302bb87df19f73
---

## Locale copy can carry bytes an eye cannot check — a Cyrillic С that looks like Latin C, a no-break space before a unit or after № — so commit supplied strings by paste and verify the code points with a script.

The language-culture holders flagged invisible or confusable bytes
three times:

- ru `map.compass.north` is «С», Cyrillic U+0421 — identical on screen
  to Latin C U+0043. "A Latin C would pass every eye and every review."
- ru `{line}` is "№ {line}" with U+00A0 between № and the number —
  "keep that byte in the fixture if you copy the value".
- ru and ka distances carry a no-break space before «м»/«км» and the
  Georgian unit.

A retyped string, a fixture written by hand, or an editor that
normalises whitespace silently swaps these, and neither `validate_i18n`
(key parity) nor review notices.

**How to apply:** when the caller commits supplied text, paste it from
the message, then check the bytes:
`python3 -c "import json;v=json.load(open('product/i18n/ru-RU.json'))['<key>'];print([hex(ord(c)) for c in v])"`.
In a widget test that asserts rendered copy, read the value from the
dictionary rather than retyping it, so the test holds the same bytes.

*Observed 2026-10-18 (flutter-dev)*

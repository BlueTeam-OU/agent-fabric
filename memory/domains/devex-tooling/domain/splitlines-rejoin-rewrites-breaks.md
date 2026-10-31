---
role: "devex-tooling"
class: domain
topic: "splitlines-rejoin-rewrites-breaks"
description: "Python str.splitlines breaks at U+2028/U+2029/U+0085/\\x0b/\\x0c/\\x1c-\\x1e too; filter lines with keepends=True and join \"\", never rejoin with \"\\n\""
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2ead64af9c4e0de0
---

## Python str.splitlines breaks at U+2028/U+2029/U+0085/\x0b/\x0c/\x1c-\x1e too; filter lines with keepends=True and join "", never rejoin with "\n"

`str.splitlines()` splits at \r\n, \r, \n and also U+2028, U+2029, U+0085, \x0b, \x0c, \x1c, \x1d, \x1e. Removing some lines and rejoining the rest with `"\n"` rewrites every one of those in the text that stays (and CRLF to LF). To drop lines and keep the rest as written: scan `s.splitlines()` (no line ends, so `$` regexes match), then filter `s.splitlines(keepends=True)` by the same indices and join with `""` — both splits break at identical places. Caught by the blind review of agent-fabric post_review.without_dispatch_headers (3cf5e3be, fixed cc2f205e, #259).

*Observed 2026-10-14 (devex-tooling)*

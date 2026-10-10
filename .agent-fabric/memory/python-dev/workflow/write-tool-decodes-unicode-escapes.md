---
role: "python-dev"
class: workflow
topic: "write-tool-decodes-unicode-escapes"
description: before writing Python with \uXXXX escapes or regexes with \s into tools/fabric/gzcoord or any fabric module — the Write tool stores raw characters, and the gzcoord guard wants re.ASCII
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 98875e52b24f3f30
---

## before writing Python with \uXXXX escapes or regexes with \s into tools/fabric/gzcoord or any fabric module — the Write tool stores raw characters, and the gzcoord guard wants re.ASCII

Two traps hit on 2026-10-07, while writing gzcoord-compose (compose.py)
and fabric-genimage (genimage.py):

1. **The Write tool decodes `\uXXXX` in file content.** A string I
   wrote as `"\u2028\u2029"` or `"\u00a0…\ufeff"` was stored as the raw
   characters. Python still runs it, but the characters are invisible in
   a diff and some tools read U+2028 and U+2029 as line breaks. After
   any Write or Edit that holds such an escape, check with
   `grep -nP '[\x{2028}\x{2029}\x{00a0}\x{feff}]' <files>`. To fix, write
   the escapes from a Python script with `\\u`, or convert every
   Zs/Zl/Zp/Cf/Cc character above 127 to an escape.
2. **tests/test_gzcoord_port.py guards the whole gzcoord package.** Every
   pattern there with `\s`, `\d`, `\w` or `\b` must carry `re.ASCII`. It
   is a package-wide scan, so a new module's own tests passing proves
   nothing. Run test_gzcoord_port.py, or the full suite, before
   delivering anything under tools/fabric/gzcoord/. See
   [[python-defaults-that-differ-from-node]] and
   [[facade-split-monkeypatch-trap]] (tests that read the package's
   text).

**Why:** the compose suite failed on the guard after review. The raw
separators passed review, tests, ruff and lint unseen.
**How to apply:** run the grep above before every commit of hand-written
Python that contains escapes. For gzcoord, run the package-wide guards
before the review, not after it.

*References: facade-split-monkeypatch-trap, python-defaults-that-differ-from-node*

*Observed 2026-10-07 (python-dev)*

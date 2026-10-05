---
role: "python-dev"
class: domain
topic: "python-defaults-that-differ-from-node"
description: porting Node to Python — the stdlib defaults that silently differ (Unicode \d, or vs ??, urllib proxy/redirect, header CRLF errors, stdout encoding)
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fd7c8512e4371a3c
---

## porting Node to Python — the stdlib defaults that silently differ (Unicode \d, or vs ??, urllib proxy/redirect, header CRLF errors, stdout encoding)

A port from Node to Python inherits Python's defaults unless each is checked. Review of agent-fabric #93 (Wave 7) found all of these, and none of them was caught by a parity corpus:
- `\d`, `\w`, `\s` and `\b` in `re` are Unicode, and so are `str.isdigit()`, `int()` and `float()`: "١٢" is 12, and "²" passes isdigit() but crashes int(). JS's are ASCII. Use re.ASCII, and isascii() before int() or float(). `int(x, 16)` also takes a sign, spaces and "_", which Number() does not.
- `a or b` treats "" as unset, where JS `??` treats it as set. Audit every `??` in the original file against its Python line; don't sample.
- urllib honours http_proxy from the environment and follows a redirect carrying Authorization to another host. For a direct call, use build_opener(ProxyHandler({}), a redirect handler whose redirect_request returns None).
- http.client's ValueError for a header with CR or LF quotes the whole header, a secret with it. That error is not a URLError, so it escapes a narrow except. Trim the value, and refuse it yourself without quoting it.
- stdout under a non-UTF-8 locale, or a lone surrogate from JSON, raises UnicodeEncodeError mid-run. reconfigure(encoding="utf-8", errors="replace") at the entry point.
- Node writes U+FFFD per lone surrogate; errors="replace" writes "?". Register an encode handler that returns the UTF-8 bytes of U+FFFD: CPython's UTF-8 encoder accepts only ASCII text back from a handler and re-raises otherwise.
- `except BaseException` around an in-process call swallows KeyboardInterrupt and SystemExit. Re-raise them first.
**Why:** the parity corpus only held inputs the old suites had, and none of them had non-ASCII digits, an empty flag, a proxy or a bad token.
**How to apply:** at the start of any JS-to-Python port, grep for each item above and fix each as a rule, with a structural test where one fits (an AST walk for re calls).

*Observed 2026-10-04 (python-dev)*

---
role: "python-dev"
class: domain
topic: "js-python-parity-at-boundaries"
description: porting Node to Python where both must answer alike — the JavaScript semantics Python gets wrong by default (JSON, strings, numbers, argv, keys, time bounds)
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7194320046ef41b4
---

## porting Node to Python where both must answer alike — the JavaScript semantics Python gets wrong by default (JSON, strings, numbers, argv, keys, time bounds)

Learnt on the Wave 8 control-plane port (#132, 2026-10-09), each one a review finding first. Each is now a helper in
tools/fabric/control/js.py with a Node-differential test (tests/test_control_js.py).
- Output JSON: json.dumps(ensure_ascii=False) writes a lone surrogate raw, then UTF-8 cannot encode it; JSON.stringify
  escapes it. NaN/Infinity are null in JS. Use a stringify that mirrors JSON.stringify.
- Input JSON: json.loads accepts NaN/Infinity (JSON.parse refuses) and raises RecursionError (not ValueError) on deep
  nesting, past `except ValueError`; Node's catch takes both.
- Numbers: float() takes "1_0" and Unicode digits and refuses 0x/0o/0b; Number() is the reverse; int("0x10",16) takes a
  second prefix. Number formatting for signed bytes: shortest digits laid out by Number::toString, not repr().
- Strings: .length / .slice are UTF-16 units; trim() is JS whitespace (U+FEFF yes, U+001C no); String(null) = "null"
  (passes a slug regex!); JS `$` never matches before a trailing \n — use fullmatch.
- Objects: Object.keys puts integer-index keys first; `??` is null-only ("" survives); a missing property is undefined
  ("undefined" in a template), not null.
- argv: execFile String()-s every argument and turns a lone surrogate into U+FFFD; subprocess raises on it.
- URLSearchParams encodes ~ and leaves *, the reverse of urlencode.
- Time bounds: urllib's timeout is per socket op; a whole-call bound needs a timer that shuts the socket — and the socket
  must be registered from connect on (create_connection keeps it private, each address gets the full bound).
**Why:** a mixed fleet (Node and Python agents) must refuse or run the same request alike; each default difference was
reachable by a relay-token holder.
**How to apply:** for any ported value that crosses a boundary (JSON in/out, argv, a URL, a length check), go through
the js helper and add the case to a Node differential, not a hand-written expected value.
Related: [[wave-8-signed-bytes-and-frozen-state]], [[python-defaults-that-differ-from-node]].

*References: python-defaults-that-differ-from-node, wave-8-signed-bytes-and-frozen-state*

*Observed 2026-10-09 (python-dev)*

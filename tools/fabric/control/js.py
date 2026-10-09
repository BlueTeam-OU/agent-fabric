"""tools/fabric/control/js.py — JavaScript's reading of a value, where the
Python control plane must judge a request exactly as the Node one does
(ADR-040 Wave 8: a mixed fleet answers alike during the rolling upgrade).

  trim(s)          String.prototype.trim(): JavaScript's WhiteSpace and
                   LineTerminator, which Python's strip() does not match
                   (U+FEFF, U+180E, U+001C..U+001F)
  length(s)        s.length: UTF-16 code units, not code points
  slice(s, n)      s.slice(0, n), in code units
  string(v)        String(v): null is "null", 5.0 is "5", [1, null] "1,"
  number(s)        Number(s) of a string: decimal, 0x/0o/0b, Infinity,
                   blank is 0, anything else NaN
  keys(d)          Object.keys(d): integer-index keys first, ascending
  truthy(v)        what `if (v)` takes
  json_parse(s)    JSON.parse(s): no NaN or Infinity, which Python's
                   json.loads takes; an integer is a double as in
                   JavaScript (rounded past 2**53, Infinity past the
                   largest); too deep a value is a ValueError
                   too, never a RecursionError past a caller's catch.
                   A named gap: Python's reader stops near 52,000 levels
                   (3.14), where Node's JSON.parse reads a million; a
                   record that deep is refused here and read there.
                   Node's own limits are its stack, not a rule (its
                   JSON.stringify overflows near 4,000), so they are not
                   copied.
  stringify(v)     JSON.stringify(v): compact, a lone surrogate escaped
                   (json.dumps(ensure_ascii=False) writes it raw, and it
                   cannot be encoded), NaN and the infinities as null,
                   UNDEFINED dropped from an object
  UNDEFINED        a missing property, as JavaScript reads one; string()
                   writes it "undefined", truthy() is False
  search_params(pairs)  new URLSearchParams(pairs).toString():
                   form-encoded, `~` encoded and `*` not, unlike urlencode
  iso_now()        new Date().toISOString(): milliseconds, then Z
  well_formed(s)   what a JavaScript string becomes as UTF-8 at a boundary
                   (execFile's argv, a write): a lone surrogate is U+FFFD

The signed bytes' own layout (JSON.stringify) is control/sign.py's
js_number and js_string, which string() reads numbers by.
"""
from __future__ import annotations

import datetime
import json
import math
import re
import urllib.parse

SPACE = ("\u0009\u000a\u000b\u000c\u000d \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
         "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff")
SPACES = re.compile(f"[{SPACE}]+")
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
# A radix's own digits only: Python's int("0x10", 16) takes a second prefix
# inside them, and Number("0x0x10") is NaN.
_RADIX = re.compile(r"0(?:([xX])([0-9a-fA-F]+)|([oO])([0-7]+)|([bB])([01]+))")
_INDEX = re.compile(r"0|[1-9][0-9]*")


def trim(s: str) -> str:
    return s.strip(SPACE)


def length(s: str) -> int:
    return len(s.encode("utf-16-le", "surrogatepass")) // 2


def slice(s: str, n: int) -> str:  # noqa: A001 — JavaScript's name, on purpose
    return s.encode("utf-16-le", "surrogatepass")[: 2 * n].decode("utf-16-le", "surrogatepass")


def string(v) -> str:
    from control.sign import js_number   # sign imports nothing of this module's
    if v is UNDEFINED:
        return "undefined"
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, float) and math.isnan(v):
        return "NaN"
    if isinstance(v, (int, float)):
        return js_number(v) if math.isfinite(float(v)) else ("Infinity" if v > 0 else "-Infinity")
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return ",".join("" if x is None else string(x) for x in v)
    return "[object Object]"


def number(s: str) -> float:
    t = trim(s)
    if t == "":
        return 0.0
    if t in ("Infinity", "+Infinity"):
        return math.inf
    if t == "-Infinity":
        return -math.inf
    if _DECIMAL.fullmatch(t):
        return float(t)
    m = _RADIX.fullmatch(t)
    if m:
        prefix, digits = next((m.group(i), m.group(i + 1)) for i in (1, 3, 5) if m.group(i))
        try:
            return float(int(digits, {"x": 16, "o": 8, "b": 2}[prefix.lower()]))
        except OverflowError:
            return math.inf     # Number("0x" + "f" * 300) is Infinity
    return math.nan


def keys(d: dict) -> list[str]:
    index = [k for k in d if _INDEX.fullmatch(k) and int(k) < 2**32 - 1]
    return sorted(index, key=int) + [k for k in d if k not in index]


def truthy(v) -> bool:
    if v is None or v is UNDEFINED or v is False or v == "":
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v != 0 and not math.isnan(v)
    return True


class _Undefined:
    __slots__ = ()

    def __repr__(self) -> str:
        return "undefined"

    def __bool__(self) -> bool:
        return False


UNDEFINED = _Undefined()


def _no_constant(name: str):
    raise ValueError(f"{name} is not JSON")


def _js_int(text: str):
    # A JSON integer is a double in JavaScript: exact up to 2**53, rounded
    # past it, Infinity past the largest double — never Python's exact
    # integer, which math.isfinite() and float() then fail on (review of
    # 0306aa27, F1). float() of the text, not of int(text): Python refuses
    # int() of more than 4,300 digits.
    if len(text) <= 17:
        n = int(text)
        if abs(n) <= 2**53:
            return n
    return float(text)


def json_parse(s: str):
    try:
        return json.loads(s, parse_constant=_no_constant, parse_int=_js_int)
    except RecursionError:
        raise ValueError("nested too deep to read") from None


def stringify(value) -> str:
    from control.sign import js_number, js_string
    out: list[str] = []
    todo: list = [("value", value)]
    while todo:
        what, item = todo.pop()
        if what == "text":
            out.append(item)
            continue
        if isinstance(item, list):
            todo.append(("text", "]"))
            for i in range(len(item) - 1, -1, -1):
                v = item[i]
                todo.append(("value", None if v is UNDEFINED else v))
                if i:
                    todo.append(("text", ","))
            todo.append(("text", "["))
        elif isinstance(item, dict):
            ks = [k for k in keys(item) if item[k] is not UNDEFINED]
            todo.append(("text", "}"))
            for i in range(len(ks) - 1, -1, -1):
                todo.append(("value", item[ks[i]]))
                todo.append(("text", js_string(ks[i]) + ":"))
                if i:
                    todo.append(("text", ","))
            todo.append(("text", "{"))
        elif item is None:
            out.append("null")
        elif item is True or item is False:
            out.append("true" if item else "false")
        elif isinstance(item, str):
            out.append(js_string(item))
        elif isinstance(item, (int, float)):
            out.append(js_number(item))
        else:
            raise TypeError(f"stringify: {type(item).__name__} is not a JSON value")
    return "".join(out)


def search_params(pairs) -> str:
    def enc(v: str) -> str:
        return urllib.parse.quote_plus(v, safe="*").replace("~", "%7E")
    return "&".join(f"{enc(string(k))}={enc(string(v))}" for k, v in (pairs.items() if isinstance(pairs, dict) else pairs))


def well_formed(s: str) -> str:
    # Through UTF-16 code units, so a pair held as two code points is one
    # character, as JavaScript holds it, and only a lone half is replaced.
    return s.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def iso_now() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


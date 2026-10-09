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
                   json.loads takes
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
_RADIX = re.compile(r"0([xXoObB])([0-9A-Za-z]+)")
_INDEX = re.compile(r"0|[1-9][0-9]*")


def trim(s: str) -> str:
    return s.strip(SPACE)


def length(s: str) -> int:
    return len(s.encode("utf-16-le", "surrogatepass")) // 2


def slice(s: str, n: int) -> str:  # noqa: A001 — JavaScript's name, on purpose
    return s.encode("utf-16-le", "surrogatepass")[: 2 * n].decode("utf-16-le", "surrogatepass")


def string(v) -> str:
    from control.sign import js_number   # sign imports nothing of this module's
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
        base = {"x": 16, "o": 8, "b": 2}[m.group(1).lower()]
        try:
            return float(int(m.group(2), base))
        except (ValueError, OverflowError):
            return math.nan
    return math.nan


def keys(d: dict) -> list[str]:
    index = [k for k in d if _INDEX.fullmatch(k) and int(k) < 2**32 - 1]
    return sorted(index, key=int) + [k for k in d if k not in index]


def truthy(v) -> bool:
    if v is None or v is False or v == "":
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v != 0 and not math.isnan(v)
    return True


def _no_constant(name: str):
    raise ValueError(f"{name} is not JSON")


def json_parse(s: str):
    return json.loads(s, parse_constant=_no_constant)


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


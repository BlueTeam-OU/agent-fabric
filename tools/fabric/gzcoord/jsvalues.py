"""The few JavaScript value rules the GZCoord tools' output and argv
depended on, so the port prints and parses what the Node did: Number() on
an argument, `undefined` in a line, a string's length in UTF-16 code
units, JSON.stringify's spelling. Each is a contract a suite or a caller
reads; none is a style."""
from __future__ import annotations

import json
import math
import re
from typing import Any

# JavaScript's whitespace, not Python's: `\\s` and .trim() there take U+FEFF
# and leave U+001C–U+001F and U+0085 alone; Python's do the opposite.
JS_SPACE = "\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"


class _Undefined:
    """JavaScript's `undefined`, where a Node line read a record field that
    was absent: String() of it is "undefined", not "null"."""

    def __repr__(self) -> str:
        return "undefined"

    def __bool__(self) -> bool:
        return False


UNDEFINED = _Undefined()


def get(d: Any, key: str) -> Any:
    """d[key] as JavaScript read it: UNDEFINED when absent."""
    return d.get(key, UNDEFINED) if isinstance(d, dict) else UNDEFINED


def nullish(v: Any) -> bool:
    """What `??` skips: undefined and null."""
    return v is None or v is UNDEFINED


def coalesce(*vs: Any) -> Any:
    for v in vs:
        if not nullish(v):
            return v
    return vs[-1]


def string(v: Any) -> str:
    """String(v): true/false, null, undefined, an integral number without
    a fraction, NaN, Infinity."""
    if v is UNDEFINED:
        return "undefined"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return "null"
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        if math.isinf(v):
            return "Infinity" if v > 0 else "-Infinity"
        if v.is_integer() and abs(v) < 1e21:
            return str(int(v))
    return str(v)


def stringify(v: Any) -> str:
    """JSON.stringify(v) for the values the tools serialise: compact,
    non-ASCII as itself; undefined stringifies to undefined (printed as
    "undefined" by String())."""
    if v is UNDEFINED:
        return "undefined"
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


# ASCII: Python's \d, int() and float() take any Unicode digit ("١٢" is 12),
# Number() only 0-9.
_DEC = re.compile(r"[+-]?(?:\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)", re.ASCII)
_INT = {"0x": 16, "0o": 8, "0b": 2}


def number(v: Any) -> float:
    """Number(v) for an argv string or a relay field: whitespace trimmed,
    "" is 0, 0x/0o/0b, Infinity, a decimal; anything else NaN."""
    if v is UNDEFINED:
        return math.nan
    if v is None or v is False:
        return 0.0
    if v is True:
        return 1.0
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(f"^[{JS_SPACE}]+|[{JS_SPACE}]+$", "", str(v))
    if s == "":
        return 0.0
    if s in ("Infinity", "+Infinity"):
        return math.inf
    if s == "-Infinity":
        return -math.inf
    base = _INT.get(s[:2].lower())
    if base:
        try:
            # int() also takes a sign, spaces, "_" and non-ASCII digits; Number() none.
            return float(int(s[2:], base)) if s[2:].isascii() and s[2:].isalnum() else math.nan
        except ValueError:
            return math.nan
    return float(s) if _DEC.fullmatch(s) else math.nan


def is_integer(x: float) -> bool:
    return not math.isnan(x) and not math.isinf(x) and float(x).is_integer()


def truthy_number(x: float) -> bool:
    return not (x == 0 or math.isnan(x))


def length(s: str) -> int:
    """String.prototype.length: UTF-16 code units — a character outside the
    Basic Multilingual Plane counts 2. The notification cap is measured in
    these, as the Node measured it."""
    return len(s) + sum(1 for ch in s if ord(ch) > 0xFFFF)


def last_newline_at_or_before(text: str, max_units: int) -> int:
    """text.lastIndexOf('\\n', max) in UTF-16 units, as a Python index into
    text; -1 when there is none."""
    units, found = 0, -1
    for i, ch in enumerate(text):
        if units > max_units:
            break
        if ch == "\n":
            found = i
        units += 2 if ord(ch) > 0xFFFF else 1
    return found

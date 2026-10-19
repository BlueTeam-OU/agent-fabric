"""runtime/claude-code/hooks/hook_jq.py — the jq the Wave 9 batch 5 guards' bash ran, read the way jq read it.

model-switch-guard.py, pipe-status-guard.py and subagent-clone-guard.py import this from their own directory
(each puts it first on sys.path: they run under `python -I`, which leaves it off). Their bash read the hook
payload with `jq -r`, wrote decisions with `jq -nc` and re-read the review fence's answer with `jq -e`/`jq -c`;
a guard's decision follows from what those calls printed and how they exited, so this module answers the same
two things, as jq 1.8 does (the host's, measured 2026-10-19):

  input     a STREAM of JSON values, whitespace between them optional; a parse error stops the stream after
            what came before it was printed. NaN reads as null and ±Infinity as ±1.7976931348623157e+308.
            A lone UTF-16 surrogate escape and a raw control character in a string are parse errors.
  per value a filter that fails on one value (indexing a string, adding a number to a string) prints
            nothing for it, and jq goes on with the next value.
  exit      non-zero when the stream ended in a parse error or when its LAST value failed; a failure
            earlier in the stream is forgotten (`[3] {"a":1}` exits 0).
  -r        a string is printed raw; anything else as JSON, a container indented by two spaces.
  -c        compact JSON, non-ASCII raw, the control characters and DEL escaped.

Where Python's rendering of a non-string still differs from jq's (jq 1.8 keeps a number's literal, `1E+2`
for 1e2; Python prints 100.0), the payload field held a number where the harness sends a string; the three
guards' decisions read strings, and the docstrings of the guards name what follows from it.
"""
from __future__ import annotations

import json
import sys

WS = " \t\n\r"
_MAX = 1.7976931348623157e308
_CONSTANTS = {"NaN": None, "Infinity": _MAX, "-Infinity": -_MAX}


class Failed(Exception):
    """A filter's runtime error on one value: jq prints nothing for it and reads on."""


class _ParseError(Exception):
    pass


def _has_lone_surrogate(value) -> bool:
    if isinstance(value, str):
        return any("\ud800" <= c <= "\udfff" for c in value)
    if isinstance(value, list):
        return any(_has_lone_surrogate(v) for v in value)
    if isinstance(value, dict):
        return any(_has_lone_surrogate(k) or _has_lone_surrogate(v) for k, v in value.items())
    return False


def _values(text: str):
    decoder = json.JSONDecoder(parse_constant=_CONSTANTS.__getitem__)
    i, n = 0, len(text)
    while True:
        while i < n and text[i] in WS:
            i += 1
        if i >= n:
            return
        try:
            value, i = decoder.raw_decode(text, i)
        except ValueError:
            raise _ParseError from None
        if _has_lone_surrogate(value):
            raise _ParseError
        yield value


def run(text: str, each) -> tuple[list, bool]:
    """`jq <filter>` over the stream in `text`: every value `each` returned (a list per input value, empty for
    jq's `empty`), and whether jq would have exited 0."""
    out: list = []
    last_failed = False
    try:
        for value in _values(text):
            try:
                results = each(value)
            except Failed:
                last_failed = True
                continue
            last_failed = False
            out.extend(results)
    except _ParseError:
        return out, False
    return out, not last_failed


def raw(value) -> str:
    """One value as `jq -r` prints it, without the newline."""
    if isinstance(value, str):
        return value
    indent = 2 if isinstance(value, (list, dict)) and value else None
    return json.dumps(value, ensure_ascii=False, indent=indent)


def captured(values: list) -> str:
    """`"$(jq -r …)"`: the values' lines, the trailing newlines dropped, as a shell variable holds them (no NUL)."""
    return "\n".join(raw(v) for v in values).rstrip("\n").replace("\0", "")


def index(value, key: str):
    """jq's `.key`: null on null, the member (or null) on an object, an error on anything else."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    raise Failed


def alt(value, default):
    """jq's `value // default`: null and false are absent."""
    return default if value is None or value is False else value


def compact(value) -> str:
    """`jq -c`, without the newline."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("\x7f", "\\u007f")


def decision(event: str, kind: str, reason: str) -> str:
    """`jq -nc --arg r "$reason" '{hookSpecificOutput:{hookEventName:…,permissionDecision:…,permissionDecisionReason:$r}}'`."""
    return compact({"hookSpecificOutput": {"hookEventName": event, "permissionDecision": kind,
                                           "permissionDecisionReason": reason}})


def env_text(value: str) -> str:
    """An environment or argv string as jq's --arg holds it: bytes that are not UTF-8 become U+FFFD."""
    return value.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def write(text: str) -> None:
    sys.stdout.buffer.write(text.encode("utf-8", "replace"))
    sys.stdout.buffer.flush()

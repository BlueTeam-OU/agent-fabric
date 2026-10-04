"""tools/fabric/gzcoord/i18n.py — the lines the GZCoord tools print, in the
language of the login that reads them. Ported from
communication/gzcoord/scripts/i18n.mjs (agent-fabric ADR-040 §7, Wave 7),
whose contract is kept:

  the default dictionary  communication/gzcoord/i18n/en-US.json, beside the
                          code and never under AGENT_FABRIC_ROOT: it is the
                          last fallback there is, and a test pointing the
                          root at a fixture names where the roles live, not
                          where the tools ship
  an active locale        identities/roles/<role>/locale/<suffix>/<tag>.json
                          under the fabric root, reached by the LOGIN's
                          suffix (language-culture-ge -> ge) under the bound
                          role, its tag read from that directory's
                          locale.json — `ge` is Georgian, not German
  GZCOORD_DEFAULT_LOCALE_ONLY
                          exactly "1" pins the ambient resolution to the
                          default locale (any other value is off); said once
                          on stderr when it suppresses a locale that exists
  stderr                  `gzcoord: <file> could not be read (<why>); …` once
                          for an unreadable default dictionary, and once per
                          unreadable locale dictionary; nothing on stdout

A language-culture holder reasons in its locale, and the fabric removes
every English it controls from that session (ADR-027). The MESSAGE is the
wire and stays as its sender wrote it; everything the tools say AROUND it
— head lines, titles, the validator's diagnostics, errors — is the
reader's, in its language (the owner, 2026-09-21; ADR-028). What is NOT in
the dictionary, deliberately: the body, the metadata keys, the type names
and `broadcast` — the wire's vocabulary, matched by name across locales.

A missing key falls back to the default rather than failing a session
start; the house standard (i18n/README.md) does not allow its clients
that, and lint keeps an incomplete dictionary from landing instead. Never
invented text.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Callable

from . import paths
from .jsvalues import string as js_string

DEFAULT_LOCALE = "en-US"
I18N_DIR = os.path.join(paths.GZCOORD_DIR, "i18n")
DEFAULT_PATH = os.path.join(I18N_DIR, f"{DEFAULT_LOCALE}.json")
DEFAULT_LOCALE_ONLY = "GZCOORD_DEFAULT_LOCALE_ONLY"

Printer = Callable[..., str]


def default_dictionary(file: str = DEFAULT_PATH) -> Any:
    with open(file, encoding="utf-8") as fh:
        return json.load(fh)


# A tool that cannot read its own default dictionary must not die of it —
# parse() runs inside callers that would read a throw as "not a GZCOORD/1
# message", and send's exit codes mean something to its callers — but it
# must not go quiet either: an empty dictionary prints every line as its
# own key, unreadable unless something says why. Degrade, and say so once
# (blind review F6 and the round after it, PR #28).
_said = False


def default_dictionary_or_empty(file: str = DEFAULT_PATH) -> dict[str, Any]:
    global _said
    try:
        d = default_dictionary(file)
        # Parsed is not usable: null, a string, a number and an array are
        # all valid JSON and none of them is a dictionary (re-review N2).
        if not isinstance(d, dict):
            raise TypeError("not an object of lines")
        return d
    except (OSError, ValueError, TypeError) as e:
        if not _said:
            _said = True
            print(f"gzcoord: {file} could not be read ({_reason(e)}); every line will print as its own key",
                  file=sys.stderr)
        return {}


def _reason(e: BaseException) -> str:
    return e.strerror if isinstance(e, OSError) and e.strerror else str(e)


def suffix(agent: str) -> str:
    """What follows the login's last dash (language-culture-ge -> ge);
    tools/fabric/launch_prompt.py::_suffix."""
    return agent[agent.rindex("-") + 1:] if "-" in agent else agent


def locale_tag(directory: str) -> str | None:
    """The locale's BCP-47 tag from its locale.json; None when absent or
    unreadable."""
    try:
        with open(os.path.join(directory, "locale.json"), encoding="utf-8") as fh:
            tag = json.load(fh).get("tag")
    except (OSError, ValueError, AttributeError):
        return None
    return tag if isinstance(tag, str) else None


# Exactly '1': truthiness would make =0, =false and =no all mean yes, the
# one reading an operator setting it that way cannot have intended (blind
# review F2 on PR #30). It governs the AMBIENT resolution only: the suites
# assert the lines the tools print, and a suite pinning English must not be
# green on a login with no locale (CI's) and red on every holder's.
def _pinned(env: dict) -> bool:
    return env.get(DEFAULT_LOCALE_ONLY) == "1"


def _locale_dir(me: dict, root: str) -> str:
    return os.path.join(root, "identities", "roles", me["role"], "locale", suffix(me["agent"]))


# A suppressed locale is visible to its reader: a holder served English, and
# losing the reminder its bridge appends, must be told why (blind review F3
# on PR #30). Said once, and only when there was something to suppress.
_pin_said = False


def _say_pinned_once(directory: str) -> None:
    global _pin_said
    if _pin_said or not os.path.exists(directory):
        return
    _pin_said = True
    print(f"gzcoord: {DEFAULT_LOCALE_ONLY}=1 — printing the default locale, not {directory}", file=sys.stderr)


def _bound(me: dict | None) -> bool:
    return bool(me and me.get("agent") and me.get("role"))


def locale_reminder(me: dict | None, root: str | None = None, env: dict | None = None) -> str:
    """The standing reminder a locale's holder reads on every drain and
    delivery — "think in <the language>", the owner's own words, in the
    locale. Not a dictionary key: there is no English line it translates.
    Empty when there is none; silenced by the same switch as every line."""
    if not _bound(me):
        return ""
    root = paths.fabric_root() if root is None else root
    env = os.environ if env is None else env
    directory = _locale_dir(me, root)
    if _pinned(env):
        _say_pinned_once(directory)
        return ""
    try:
        with open(os.path.join(directory, "locale.json"), encoding="utf-8") as fh:
            r = json.load(fh).get("reminder")
    except (OSError, ValueError, AttributeError):
        return ""
    return r if isinstance(r, str) else ""


def dictionary_path(me: dict | None, root: str | None = None, env: dict | None = None) -> str | None:
    """The dictionary file for this login, or None for the default locale."""
    if not _bound(me):
        return None
    root = paths.fabric_root() if root is None else root
    env = os.environ if env is None else env
    directory = _locale_dir(me, root)
    if _pinned(env):
        _say_pinned_once(directory)
        return None
    tag = locale_tag(directory)
    if not tag or tag == DEFAULT_LOCALE:
        return None
    file = os.path.join(directory, f"{tag}.json")
    return file if os.path.exists(file) else None


def dictionary(me: dict | None, root: str | None = None, file: str = DEFAULT_PATH,
               env: dict | None = None) -> dict[str, Any]:
    """The default locale, with an active locale's own non-empty string
    values over the keys the default has."""
    base = default_dictionary_or_empty(file)
    p = dictionary_path(me, root, env)
    if not p:
        return base
    try:
        with open(p, encoding="utf-8") as fh:
            loc = json.load(fh)
        for k, v in loc.items():
            if isinstance(v, str) and v != "" and k in base:
                base[k] = v
    except (OSError, ValueError, AttributeError) as e:
        # The default still prints — this is a session start — but not
        # silently: a broken dictionary is not a missing one.
        print(f"gzcoord: {p} could not be read ({_reason(e)}); printing the default locale", file=sys.stderr)
    return base


_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def fill(template: str, vars: dict | None = None) -> str:
    """`{name}` from vars. A placeholder the caller did not supply is left
    standing rather than blanked: a translation that invented one is then
    visible in the line instead of eating the value beside it."""
    vars = vars or {}
    return _PLACEHOLDER.sub(lambda m: js_string(vars[m.group(1)]) if m.group(1) in vars else m.group(0), template)


def printer(d: dict) -> Printer:
    """t('inbox.head', {...}). An unknown key prints as itself — a bug
    report, not a crash; the i18n suite is where it is caught."""
    def t(key: str, vars: dict | None = None) -> str:
        return fill(d[key], vars) if key in d else key
    return t


def t_for(me: dict | None, **opts) -> Printer:
    """The printer for a given login. `me` is passed, never discovered here:
    whoami() lives in gzmsg, and the validator there takes its diagnostics
    from this module."""
    return printer(dictionary(me, **opts))

"""tools/fabric/launcher/holder.py — the holder's addenda of the bound role, read for the prompt (agent-fabric ADR-060).
A part of tools/fabric/launch.py, whose docstring is the contract.

The reading is addenda.py's, run as a helper like the identity and the
prompt render: by path, under -I, its refusal one line on stderr. Here the
catalogue's policy for the role, the file the render takes, and the holder's
locale resolved from what was read (rule 8)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

from fabric_launcher.base import HERE, _load, die, helper, roots, stripped

HOLDER_FILE = "launch-holder.json"
# What the resolved locale puts in the session's environment: TZ, which every
# process of the session reads, and the country the locale search server reads;
# neither reader opens the store. The tag is not exported: its one consumer
# besides the launcher is the agent-file installer, which takes it as --locale.
LOCALE_ENV = ("TZ", "AGENT_FABRIC_SEARCH_COUNTRY")
# The TZ this launch set, so a restart (which re-executes with that environment) can tell it from the operator's.
LAUNCH_TZ = "AGENT_FABRIC_LAUNCH_TZ"
# The TZ the operator's own environment had before this launch overwrote it, so that a restart which knows no
# timezone can put it back instead of leaving the session on UTC.
OPERATOR_TZ = "AGENT_FABRIC_OPERATOR_TZ"
# The one definition of a valid locale tag and country: the validator the
# install and the render already run.
_check = _load("fabric_addenda_check", os.path.join(HERE, "addenda_check.py"))


def policy(fabric_root: str, role: str) -> str:
    """holders_specialize of the role in the catalogue, "optional" when the
    entry leaves it out (rule 7). A catalogue that is missing or cannot be
    read, a role it does not list, or a value that is neither stops the
    launch: the flag exists so that a role whose shared text names no
    jurisdiction is never launched without addenda, and a policy that cannot
    be read must not turn into "optional"."""
    path = roots.role_catalog(engine=fabric_root, environ=os.environ)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as e:
        die(f"{path} could not be read ({type(e).__name__}), so whether {role} needs holder addenda is unknown.")
    entries = [r for r in doc.get("roles", []) if isinstance(r, dict) and r.get("id") == role] if isinstance(doc, dict) else []
    if not entries:
        die(f"{path} does not list the role {role}, so whether it needs holder addenda is unknown.")
    value = entries[0].get("holders_specialize", "optional")
    if value not in ("optional", "required"):
        die(f"{path}: holders_specialize of {role} is {value!r}, not optional or required.")
    return value


def read(fabric_root: str, agent: str, role: str, state_dir: str) -> tuple[str, str] | None:
    """(store sha, addenda commit) and the Holder at state_dir/launch-holder.json,
    or None with no such file left over from an earlier launch: no addenda."""
    out = os.path.join(state_dir, HOLDER_FILE)
    try:
        os.unlink(out)
    except FileNotFoundError:
        pass
    r = helper([sys.executable, "-I", os.path.join(HERE, "addenda.py"), "--login", agent, "--role", role,
                "--policy", policy(fabric_root, role), "--out", out])
    if r is None or r.returncode != 0:
        die(f"the holder addenda of role {role} could not be read (tools/fabric/addenda.py); the launch stops.")
    answer = stripped(r).split()
    if not answer:
        return None
    if len(answer) != 2:
        die("tools/fabric/addenda.py answered something else than a store sha and a commit.")
    return answer[0], answer[1]


@dataclass(frozen=True)
class Locale:
    tag: str
    timezone: str | None
    country: str | None

    @property
    def valid_tag(self) -> str | None:
        # A suffix that is no locale tag ("03" of python-dev-03) names no locale: not a bare number.
        return self.tag if _check.LOCALE_RE.fullmatch(self.tag) else None

    def exports(self) -> dict[str, str | None]:
        return dict(zip(LOCALE_ENV, (self.timezone, self.country)))


def _held_holder_json(state_dir: str, held: bool) -> dict | None:
    """holder.json as the launcher's read left it in launch-holder.json; None
    when no addenda were read or the store has no holder.json. The file is the
    launcher's own, written a moment ago: one that does not parse is a fault,
    and a locale guessed from the suffix would hide it."""
    if not held:
        return None
    path = os.path.join(state_dir, HOLDER_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        value = doc["holder"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        die(f"{path} could not be read ({type(e).__name__}); the holder's locale is unknown, the launch stops.")
    if value is not None and not isinstance(value, dict):
        die(f"{path}: holder is not an object; the holder's locale is unknown, the launch stops.")
    return value


def _locale_path(fabric_root: str, tag: str) -> str:
    return os.path.join(roots.locale_dir("language-culture", tag, engine=fabric_root, environ=os.environ), "locale.json")


def _locale_json(fabric_root: str, tag: str) -> dict:
    """language-culture's locale.json of the tag, or {} when the fabric authored none. Its deployment values are only
    the fallback of a holder that names none. A file that is absent is no facts; one that is there and unusable stops
    the launch, because dropping its timezone silently would hide it."""
    path = _locale_path(fabric_root, tag)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        die(f"{path} could not be read ({type(e).__name__}); the holder's timezone and search country are unknown, the launch stops.")
    if not isinstance(doc, dict):
        die(f"{path} is not an object; the holder's timezone and search country are unknown, the launch stops.")
    return doc


def resolve_locale(fabric_root: str, suffix: str, state_dir: str, held: bool) -> Locale:
    """The locale the session renders and searches in (ADR-060 rule 8): holder.json's locale, the login's suffix only
    while the holder has no holder.json; its timezone and search country from holder.json, else from the locale.json
    of that locale (serpapi.gl is the country the search answers as). Each is None when nobody names it."""
    data = _held_holder_json(state_dir, held)
    tag = suffix
    if data is not None:
        tag = data.get("locale")
        if not (isinstance(tag, str) and _check.LOCALE_RE.fullmatch(tag)):
            die("holder.json names no valid locale; the launch stops.")
    fallback = _locale_json(fabric_root, tag)
    timezone = (data or {}).get("timezone", fallback.get("timezone"))
    search = (data or {}).get("search")
    serpapi = fallback.get("serpapi")
    country = search.get("country") if isinstance(search, dict) and "country" in search else \
        serpapi.get("gl") if isinstance(serpapi, dict) else None
    if isinstance(timezone, str) and timezone:
        source = "holder.json" if "timezone" in (data or {}) else _locale_path(fabric_root, tag)
        try:
            known = _check._is_iana(timezone)
        except RuntimeError as e:
            # Unknown stays unknown: no tz database means the name cannot be judged, neither valid nor invalid.
            die(f"{source} names a timezone that cannot be checked: {e}; the launch stops.")
        if not known:
            # Unlike a name nothing read, TZ sets the clock of every process of the session, and an unknown name is read as UTC without a word.
            die(f"the timezone in {source} is no IANA timezone name (the rule of holder.json's `timezone`); the launch stops.")
    return Locale(tag, timezone if isinstance(timezone, str) and timezone else None,
                  country if isinstance(country, str) and country else None)



def settle_tz(env: dict[str, str], timezone: str | None) -> None:
    """Put the holder's timezone in env's TZ, keeping the operator's own TZ apart from it. A restart re-executes
    with the environment the first launch left, so what TZ holds is the operator's only while it is not the value
    this launch family stamped: the operator's is stamped beside (OPERATOR_TZ) and goes back when a later launch
    knows no timezone, and is never replaced by a stamped value."""
    stamped = env.pop(LAUNCH_TZ, None)
    operator = env.pop(OPERATOR_TZ, None)
    if stamped is None or env.get("TZ") != stamped:
        operator = env.get("TZ")    # TZ is the operator's own (or was changed since): it is what to restore
    if timezone:
        env["TZ"] = timezone
        env[LAUNCH_TZ] = timezone
        if operator is not None:
            env[OPERATOR_TZ] = operator
    elif stamped is not None and env.get("TZ") == stamped:
        if operator is not None:
            env["TZ"] = operator
        else:
            env.pop("TZ")

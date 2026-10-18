"""tools/fabric/launch_locale.py — the locale the launcher resolved for this login (agent-fabric ADR-060 rule 8).

The launcher writes it once per launch to <state dir>/launch-locale.json
({"locale": "<tag>"}), beside binding.json. Readers that render or search in
the holder's locale (gzcoord's i18n, the activity op) read this file and never
the store and never the login's name: a login's suffix is no locale. The
record is the locale of the login's LAST launcher run (--print and --help
write it too, with the same answer for the same store); no file, or one that
cannot be used, is the default locale, "en" — except that a session launched before the
record existed is read from launch-holder.json (holder.locale), which every launch that read a holder.json wrote.

Stdlib only, loaded by path from the launcher and imported by the readers."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping

FILE = "launch-locale.json"
DEFAULT = "en"
# The launcher's own record of holder.json (launcher/holder.py HOLDER_FILE), the older source of the locale.
HOLDER_FILE = "launch-holder.json"
# addenda_check.LOCALE_RE, restated: the tag becomes a directory name, so the reader checks it itself.
TAG_RE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*")


def state_dir(agent: str, environ: Mapping[str, str] | None = None) -> str:
    """runtime/identity.py's agent_state_dir() for `agent`, without importing it."""
    environ = os.environ if environ is None else environ
    override = environ.get("AGENT_FABRIC_STATE_DIR")
    root = os.path.abspath(override) if override else os.path.join(
        environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"), "agent-fabric")
    return os.path.join(root, "agents", agent)


def record(directory: str, tag: str) -> None:
    """Replace the launch record whole, so a reader never sees half of it."""
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"locale": tag}, fh)
            fh.write("\n")
        os.replace(tmp, os.path.join(directory, FILE))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _tag_in(path: str, pick) -> str | None:
    """The valid tag `pick` takes from the JSON file at `path`; None when the file is absent (or, for the holder
    file, names no holder). A file that is there and unusable is said on stderr and is None as well: both files are
    the launcher's own, so it is a fault, not an absence."""
    try:
        with open(path, encoding="utf-8") as fh:
            tag = pick(json.load(fh))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"launch-locale: {path} could not be read ({type(e).__name__}); using the default locale", file=sys.stderr)
        return None
    if tag is _NO_HOLDER:
        return None
    if not (isinstance(tag, str) and TAG_RE.fullmatch(tag)):
        print(f"launch-locale: {path} names no valid locale; using the default locale", file=sys.stderr)
        return None
    return tag


_NO_HOLDER = object()


def _holder_locale(doc: dict) -> object:
    holder = doc["holder"]
    return _NO_HOLDER if holder is None else holder["locale"]


def read(agent: str, environ: Mapping[str, str] | None = None) -> str:
    """The tag the launcher recorded for `agent`; "en" when it recorded none. A record that is there but
    unusable is also "en" and said on stderr, since it is the launcher's own file and a fault, not an absence.
    A session launched before launch-locale.json existed has only launch-holder.json (holder.locale); that file
    answers until a relaunch writes the record. Never the login's name."""
    directory = state_dir(agent, environ)
    path = os.path.join(directory, FILE)
    if os.path.exists(path):
        return _tag_in(path, lambda doc: doc["locale"]) or DEFAULT
    return _tag_in(os.path.join(directory, HOLDER_FILE), _holder_locale) or DEFAULT

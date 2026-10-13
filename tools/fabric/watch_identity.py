#!/usr/bin/env python3
"""tools/fabric/watch_identity.py — who this account is and what it runs, for fabric-watch's identity header
(agent-fabric ADR-056 rules 1, 2 and 4).

  persona(...)        the agent's persona: its display name and the avatar file to show.
      name     "AI <first name> <surname>" from settings/profile.json in this login's store checkout, the surname
               from identities/personas/claims.json (keyed by the agent id, read from the store's .agent-id) when it
               has one; with no profile, "AI <surname>" from the claim alone; else None, and the caller shows the
               login alone. The name is NEVER shown without its "AI".
      avatar   settings/avatar.png in the store checkout, else the candidate the profile names (avatar.candidate) at
               <avatars>/<agent id>/<n>.png, else None. Only regular files, no link followed (avatar.read_file).
      Of the store checkout it reads exactly three files, settings/profile.json, settings/avatar.png (the avatar's own reader) and .agent-id — never env/, where the
      encrypted secrets are, and never lists the directory. A profile that is not what persona-profile.schema.json
      describes (an object with a first_name and a surname that are plain text of a sane length) is no profile.
  running_harness()   "claude" or "codex": which of the two has a process of this account (claude first), by the Name
                      line of /proc/<pid>/status, or None.
  version_line()      the first line of `<harness> --version`, read once by the caller, or None.
  model_lines()       the session model and effort and the second engine, from fabric-status --json's document.

Every string it returns is someone's text and goes through fabric-watch's printable() before the terminal.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

import avatar

AVATARS = "/usr/local/share/agent-fabric/avatars"
AGENT_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
NAME_MAX = 40
JSON_MAX = 64 * 1024
VERSION_TIMEOUT_S = 20
HARNESSES = ("claude", "codex")


@dataclass
class Persona:
    name: str | None = None            # "AI June Leavitt", "AI Leavitt", or None
    avatar_path: str | None = None
    agent_id: str | None = None


def store_dir(environ: dict[str, str]) -> str:
    return environ.get("AGENT_FABRIC_SECRET_STORE") or os.path.join(environ.get("HOME") or os.path.expanduser("~"), ".local", "share", "agent-fabric", "secrets")


def _inside(store: str, path: str) -> bool:
    """A committed symlink in the checkout (settings -> elsewhere) must not lead the reads out of it: the file's real
    place is under the store's real place. The last component is the reader's own O_NOFOLLOW."""
    root = os.path.realpath(store)
    return os.path.realpath(os.path.dirname(path)).startswith(root + os.sep) or os.path.realpath(os.path.dirname(path)) == root


def _read_small(path: str, store: str | None = None) -> bytes | None:
    if store is not None and not _inside(store, path):
        return None
    try:
        data = avatar.read_file(path)
    except avatar.Refused:
        return None
    return data if len(data) <= JSON_MAX else None


def _json(path: str, store: str | None = None) -> dict | None:
    data = _read_small(path, store)
    if data is None:
        return None
    try:
        doc = json.loads(data)
    except (ValueError, RecursionError):
        return None
    return doc if isinstance(doc, dict) else None


def _name(value: object) -> str | None:
    """A first name or a surname: text of 1..NAME_MAX characters with no control character."""
    if isinstance(value, str) and 1 <= len(value) <= NAME_MAX and value.isprintable():
        return value
    return None


def persona(environ: dict[str, str], claims_path: str, avatars: str = AVATARS) -> Persona:
    store = store_dir(environ)
    raw_id = _read_small(os.path.join(store, ".agent-id"), store)
    agent_id = raw_id.decode("ascii", "replace").strip() if raw_id is not None else None
    if agent_id is not None and not AGENT_ID.fullmatch(agent_id):
        agent_id = None
    out = Persona(agent_id=agent_id)
    profile = _json(os.path.join(store, "settings", "profile.json"), store)
    first, surname = (_name(profile.get("first_name")), _name(profile.get("surname"))) if profile else (None, None)
    if not (first and surname):
        first = surname = None                        # half a profile is no profile
    claims = (_json(claims_path) or {}).get("claims") if agent_id else None
    claimed = _name(claims.get(agent_id)) if isinstance(claims, dict) else None
    surname = claimed or surname                      # claims.json wins over the profile on the surname (persona-profile schema)
    if first and surname:
        out.name = f"AI {first} {surname}"
    elif surname:
        out.name = f"AI {surname}"
    accepted = os.path.join(store, "settings", "avatar.png")
    if os.path.isfile(accepted) and not os.path.islink(accepted) and _inside(store, accepted):
        out.avatar_path = accepted
    elif first and surname and agent_id and isinstance(profile, dict):   # a candidate is named by a profile that names a person
        pic = profile.get("avatar")
        n = pic.get("candidate") if isinstance(pic, dict) else None
        if type(n) is int and 1 <= n <= 999:
            candidate = os.path.join(avatars, agent_id, f"{n}.png")
            out.avatar_path = candidate if os.path.isfile(candidate) and not os.path.islink(candidate) else None
    return out


def running_harness(uid: int | None = None, proc: str = "/proc") -> str | None:
    uid = os.geteuid() if uid is None else uid
    found: set[str] = set()
    try:
        names = [n for n in os.listdir(proc) if n.isdigit()]
    except OSError:
        return None
    for pid in names:
        try:
            with open(os.path.join(proc, pid, "status"), encoding="utf-8", errors="replace") as fh:
                fields = {k: v.strip() for k, _, v in (line.partition(":") for line in fh)}
            comm = fields.get("Name", "")                       # the kernel's comm, as /proc/<pid>/comm
            if comm in HARNESSES and fields.get("Uid", "").split()[1] == str(uid):
                found.add(comm)
        except (OSError, IndexError):
            continue
    return next((h for h in HARNESSES if h in found), None)


def version_line(harness: str, path: str | None = None) -> str | None:
    """The first line `<harness> --version` prints: an argument list, a timeout, no shell, a command that is not there
    or does not answer is None. Whatever it prints is text and goes through printable()."""
    binary = shutil.which(harness, path=path)
    if binary is None:
        return None
    try:
        r = subprocess.run([binary, "--version"], capture_output=True, text=True, errors="replace", timeout=VERSION_TIMEOUT_S,
                           stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (r.stdout or "").strip().splitlines()
    return lines[0][:80] if r.returncode == 0 and lines else None


def model_lines(status: dict | None) -> dict[str, str | None]:
    """{"model", "effort", "engine"} from fabric-status --json: the session's model and effort level, and the first of
    the second engines it lists. A key the document lacks is None, never a guess."""
    api = status.get("api") if isinstance(status, dict) else None
    model = api.get("session_model") if isinstance(api, dict) else None
    effort = status.get("session_effort") if isinstance(status, dict) else None
    level = next((effort.get(k) for k in ("reported", "launched", "asked") if isinstance(effort, dict) and effort.get(k)), None)
    engines = status.get("engines") if isinstance(status, dict) else None
    engine = None
    if isinstance(engines, dict) and engines:
        key, value = next(iter(engines.items()))
        engine = f"{key}: {str(value).split(' (from', 1)[0]}"[:80]
    return {"model": model if isinstance(model, str) else None, "effort": level if isinstance(level, str) else None, "engine": engine}

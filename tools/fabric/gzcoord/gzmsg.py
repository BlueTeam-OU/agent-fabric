"""tools/fabric/gzcoord/gzmsg.py — the GZCOORD/1 message validator, its
parser and normalizer, the agent's identity, and the `gzmsg` command.
Ported from communication/gzcoord/scripts/gzmsg.mjs (agent-fabric ADR-040
§7, Wave 7); that path is now a shim that runs this.

CONTRACT, frozen from the Node:
  argv      validate <file> [--taxonomy <path> | --no-taxonomy]
            normalize <file>
            new-id
            A flag not declared for the command, a valued flag with no
            value or given twice, or a second positional: `gzmsg <cmd>:
            <why>` on stderr, exit 2, before anything is read. An unknown
            command: the usage line on stderr, exit 2.
  env       AGENT_FABRIC_ROOT (where identities/roles/catalog.json and
            runtime/identity.py are read), AGENT_FABRIC_STATE_DIR /
            XDG_STATE_HOME (the binding's directory), and i18n's
            GZCOORD_DEFAULT_LOCALE_ONLY
  stdout    validate: `valid GZCOORD/1 message`; normalize: the normalized
            text, with no newline added; new-id: one UUIDv7
  stderr    validate: `warning: <w>` for each warning (on both paths: a
            warning is often the cause the errors describe from
            downstream), then the errors one per line on failure
  exit      0 valid / printed; 1 invalid; 2 usage. A file that cannot be
            read, or a catalogue that does not load, ends the command with
            `gzmsg: <why>` and exit 1 (the Node threw: the same status).

The diagnostics are dictionary lines (i18n), in the reading login's
language; the wire's vocabulary — keys, type names — is never translated.

JavaScript's whitespace, not Python's: the Node's `\\s` and `.trim()` take
U+FEFF and leave U+001C–U+001F and U+0085 alone, and Python's do the
opposite. A message is judged the same in both, so JS_SPACE below is what
every whitespace test here uses.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pwd
import re
import secrets
import socket
import sys
import time
from bisect import bisect_right
from typing import Any

from . import i18n, paths
from .jsvalues import JS_SPACE
from ._widths import EMOJI, ZERO

_JS_TRIM = re.compile(f"^[{JS_SPACE}]+|[{JS_SPACE}]+$")


def js_trim(s: str) -> str:
    return _JS_TRIM.sub("", s)


def js_lstrip(s: str) -> str:
    return re.sub(f"^[{JS_SPACE}]+", "", s)


# The validator's own English, for a caller that passes no printer — the
# CLI outside a session, a test. Read once, lazily, and never raising:
# parse() runs inside callers that read any exception as "not a GZCOORD/1
# message", so a filesystem fault here would silently reclassify every
# message on the channel instead of being reported (blind review F6 on PR
# #28). An empty dictionary degrades to key-named lines: loud and alive.
_EN: i18n.Printer | None = None


def en() -> i18n.Printer:
    global _EN
    if _EN is None:
        _EN = i18n.printer(i18n.default_dictionary_or_empty())
    return _EN


# SPEC §8: self-announcements, retired — presence is the deployment's to
# answer. A parser rejects them (§18); the inbox acknowledges one an old
# session still sends and delivers nothing.
RETIRED_TYPES = ("HELLO", "GOODBYE")
CORE_TYPES = frozenset(("INFO", "OBSERVATION", "QUESTION", "REQUEST", "REVIEW", "DECISION", "HANDOFF", "REPLY"))
FORBIDDEN = frozenset((
    "MODEL", "PROVIDER", "WORKING-DIRECTORY", "WORKING_DIRECTORY",
    "TOKEN-BUDGET", "TOKEN_BUDGET", "REASONING-BUDGET", "REASONING_BUDGET",
    "SUBAGENT-DEPTH", "SUBAGENT-LIMIT", "SUBAGENT_LIMIT",
    "TELEGRAM-BOT", "TELEGRAM_BOT", "TELEGRAM-BOT-USERNAME", "TELEGRAM-CHAT-ID",
    "BOT-TOKEN", "BOT_TOKEN", "SLACK-CHANNEL-ID", "DISCORD-GUILD-ID",
))
ADDRESS = re.compile(r"[a-z0-9._-]+/[a-z0-9._-]+")

# Every common metadata field the spec names (§7). Used only to ask whether
# an unknown key looks like a misspelling of one — never to reject: §6
# requires unknown metadata to be preserved, which is how the protocol
# extends.
KNOWN_KEYS = ("FROM", "ROLE", "PROJECT", "TO", "TO-ROLE", "BROADCAST", "MESSAGE-ID", "IN-REPLY-TO",
              "REPOSITORY", "BRANCH", "COMMIT", "REPLY-EXPECTED", "SUBJECT", "SPECIALTIES", "CAPABILITIES")
# An id-shaped value: a UUID (the deployment mints UUIDv7), or the retired
# `<instance>-NNNN` counter form still seen in older traffic.
ID_SHAPED = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[a-z0-9._-]+-\d{4}")
_UNEXPANDED = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")


def id_complaint(key: str, value: str, t: i18n.Printer | None = None) -> str | None:
    """What an id field holds when it is NOT id-shaped, as a sentence the
    sender can act on. SPEC §7.2 makes the id opaque, so the validator only
    warns; send refuses. The literal "$ID" reached the channel once (seq
    3445, 2026-09-20): a compose step wrote the shell variable's name
    instead of its value, and nothing said so until the message was read
    back with "$ID" where the join key should be."""
    t = t or en()
    if ID_SHAPED.fullmatch(value):
        return None
    if _UNEXPANDED.fullmatch(value):
        return t("validate.id-unexpanded", {"key": key, "value": value})
    return t("validate.id-not-minted", {"key": key, "value": value})


def _edit_distance(a: str, b: str) -> int:
    d = [[i] + [0] * len(b) for i in range(len(a) + 1)]
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (0 if a[i - 1] == b[j - 1] else 1))
    return d[len(a)][len(b)]


def nearest_known_key(key: str) -> str | None:
    """A known field this unknown key was plausibly meant to be: the key is
    a whole hyphen-separated run inside it (ID inside MESSAGE-ID), or it is
    within two edits of it."""
    if key in KNOWN_KEYS:
        return None
    kp = key.split("-")
    for known in KNOWN_KEYS:
        np_ = known.split("-")
        for i in range(len(np_) - len(kp) + 1):
            if np_[i:i + len(kp)] == kp and len(kp) < len(np_):
                return known
    return next((k for k in KNOWN_KEYS if _edit_distance(key, k) <= 2), None)


# Terminal columns a line occupies (gzmsg.mjs's reasoning, kept): wide is
# the wcwidth range table (Wide and Fullwidth, halfwidth forms excluded)
# plus emoji-presentation characters; combining and format characters are
# 0; a tab advances to the next multiple of 8; everything else is 1.
# Emoji_Presentation, not Extended_Pictographic: the latter includes
# text-default symbols (©, ™, ↔, ❤) that render in one column. A regional
# indicator is 1 so a flag pair is 2. East Asian Ambiguous characters and
# VS16-forced emoji count 1, as `wc -L` does; U+3248–324F is 2 because it
# sits inside the CJK block the table takes whole. A wholly Wide block runs
# to the block end, since a range pinned to an assignment silently drops
# every later one; three stop short on purpose — FE10–FE19, FE50–FE6B,
# 1F200–1F26F — because the next code point is zero-width (U+FE20) or wide
# by another rule (U+1F300). A mixed block stops at its last wide code
# point and must not be "finished" to the block end: 40 card suits would
# report 81 columns.
WIDE_RANGES = (
    (0x1100, 0x115F), (0x2329, 0x232A), (0x2630, 0x2637), (0x268A, 0x268F),
    (0x2E80, 0x303E), (0x3041, 0x33FF), (0x3400, 0x4DBF), (0x4DC0, 0x4DFF),
    (0x4E00, 0x9FFF), (0xA000, 0xA4CF), (0xA960, 0xA97F), (0xAC00, 0xD7A3),
    (0xF900, 0xFAFF), (0xFE10, 0xFE19), (0xFE30, 0xFE4F), (0xFE50, 0xFE6B),
    (0xFF00, 0xFF60), (0xFFE0, 0xFFE6),
    (0x16FE0, 0x16FFF), (0x17000, 0x18AFF), (0x18B00, 0x18CFF), (0x18D00, 0x18DFF),
    (0x1AFF0, 0x1AFFF), (0x1B000, 0x1B2FF), (0x1D300, 0x1D376), (0x1F200, 0x1F26F),
    (0x20000, 0x2FFFD), (0x30000, 0x3FFFD),
)


def _in(ranges: tuple, cp: int, starts: list[int]) -> bool:
    i = bisect_right(starts, cp) - 1
    return i >= 0 and ranges[i][0] <= cp <= ranges[i][1]


_ZERO_STARTS = [r[0] for r in ZERO]
_EMOJI_STARTS = [r[0] for r in EMOJI]


def _is_wide(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in WIDE_RANGES) or _in(EMOJI, cp, _EMOJI_STARTS)


def columns(line: str) -> int:
    w = 0
    for ch in line:
        if ch == "\t":
            w += 8 - (w % 8)
            continue
        cp = ord(ch)
        if _in(ZERO, cp, _ZERO_STARTS):
            continue
        w += 2 if _is_wide(cp) else 1
    return w


class NotGzcoord(ValueError):
    """The first line is not a GZCOORD/1 header: nothing after it can be read."""


_HEADER = re.compile(r"\[GZCOORD/1\] ([A-Z][A-Z0-9-]*)")
_MARKER = re.compile(r"[A-Z][A-Z0-9-]*:")
_KEY_LINE = re.compile(r"[A-Z][A-Z0-9-]*: ")


def _lines(text: str) -> list[str]:
    # A byte-order mark is an encoding artefact, not the first character of
    # the header; some editors prepend one on save.
    return (text[1:] if text.startswith("﻿") else text).replace("\r\n", "\n").split("\n")


def parse(text: str, t: i18n.Printer | None = None) -> dict:
    """{type, metadata, sections, malformed, duplicateKeys} — the Node's
    shape and key names, which the inbox's JSON and the journal carry."""
    t = t or en()
    lines = _lines(text)
    first = lines.pop(0) if lines else ""
    m = _HEADER.fullmatch(first)
    if not m:
        raise NotGzcoord(t("validate.bad-first-line"))
    metadata: dict[str, str] = {}
    duplicate: list[str] = []
    sections: dict[str, str] = {}
    malformed: list[str] = []
    current = None
    in_sections = False
    for line in lines:
        if _MARKER.fullmatch(line):
            in_sections = True
            current = line[:-1]
            # A repeated marker resumes its section: the grammar does not
            # require section names to be unique, so resetting here would
            # drop the earlier block from a message still called valid.
            sections.setdefault(current, "")
            continue
        if not in_sections and _KEY_LINE.match(line):
            key = line[:line.index(":")]
            # A repeated key has no defined meaning (SPEC §6 gives a key no
            # resume rule); collapsing silently let an invalid earlier value
            # hide behind a valid later one.
            if key in metadata and key not in duplicate:
                duplicate.append(key)
            metadata[key] = js_trim(line[line.index(":") + 1:])
            continue
        if current is not None:
            sections[current] += ("\n" if sections[current] else "") + line
        elif js_trim(line) != "":
            malformed.append(line)
    return {"type": m.group(1), "metadata": metadata, "sections": sections,
            "malformed": malformed, "duplicateKeys": duplicate}


# WHO AM I. The agent is the Linux login of the effective user, and the one
# place that derivation lives is runtime/identity.py — this asks it, in
# this process (the Node ran it as `python3 identity.py --json`; the answer
# is the same dict). If it cannot answer, the fallback computes the same
# thing (effective uid -> login) and reads the same binding file by the
# same path rule; it never looks at the working directory's name.
def binding_file(agent: str) -> str:
    # Set but empty is set, as `??` read both in the Node.
    base = os.environ.get("AGENT_FABRIC_STATE_DIR")
    if base is None:
        state = os.environ.get("XDG_STATE_HOME")
        base = os.path.join(os.path.join(os.path.expanduser("~"), ".local", "state") if state is None else state,
                            "agent-fabric")
    return os.path.join(base, "agents", agent, "binding.json")


def _identity_module(root: str):
    spec = importlib.util.spec_from_file_location("fabric_runtime_identity", os.path.join(root, "runtime", "identity.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def whoami() -> dict:
    try:
        me = _identity_module(paths.fabric_root()).resolve_context()
        if not isinstance(me, dict) or not isinstance(me.get("agent"), str):
            raise TypeError("no agent")
        me = json.loads(json.dumps(me))
        me["binding"] = binding_file(me["agent"])
        return me
    except (Exception, SystemExit):  # noqa: BLE001 — any failure is the Node's non-zero exit: the fallback
        pass
    agent = pwd.getpwuid(os.geteuid()).pw_name
    binding: Any = {}
    try:
        with open(binding_file(agent), encoding="utf-8") as fh:
            binding = json.load(fh)
    except (OSError, ValueError):
        pass
    if not isinstance(binding, dict):
        binding = {}
    return {"agent": agent, "host": socket.gethostname().split(".")[0], "role": binding.get("role"),
            "project": binding.get("project"), "working_copy": binding.get("working_copy"),
            "binding": binding_file(agent), "fallback": True}


class Taxonomy:
    """A deployment's role catalogue (SPEC §4: the core keeps no enum; a
    deployment MAY publish one — agent-fabric's is
    identities/roles/catalog.json): slug (the catalogue id, what goes on
    the wire) -> title. The catalogue is the only source a RECEIVING
    validator can consult: committed and identical in every clone, where a
    sender's role record is on the sender's disk."""

    def __init__(self, path: str, roles: dict[str, str]):
        self.path, self.roles = path, roles


def load_taxonomy(file: str) -> Taxonomy:
    with open(file, encoding="utf-8") as fh:
        doc = json.load(fh)
    roles: dict[str, str] = {}
    for r in (doc.get("roles") or []) if isinstance(doc, dict) else []:
        if isinstance(r, dict) and r.get("id") and r.get("title"):
            roles[r["id"]] = r["title"]
    if not roles:
        raise ValueError(f"{file} holds no roles with id and title")
    return Taxonomy(file, roles)


def recorded_role(taxonomy: Taxonomy | None, me: dict | None = None) -> dict:
    """The AGENT's active-role record (the runtime binding role.py writes).
    Four outcomes, kept distinct because a record that fails to name a
    usable role must never pass as "no record" and fall through to a guess
    from the address: none, or one with no role; a catalogue role; present
    but unreadable (a warning, the caller decides); a role the catalogue
    lacks (an error: the agent asserts a role the deployment does not
    know). The warning states the cause only."""
    if taxonomy is None or not taxonomy.path:
        return {"role": None}
    me = whoami() if me is None else me
    file = me.get("binding") or binding_file(me["agent"])
    if me.get("role") is None:
        if not os.path.exists(file):
            return {"role": None}
        try:
            with open(file, encoding="utf-8") as fh:
                json.load(fh)
        except (OSError, ValueError) as e:
            return {"role": None, "warning": f"{file} could not be read ({e})"}
        return {"role": None, "warning": f"{file} records no role"}
    if me["role"] not in taxonomy.roles:
        return {"role": None, "error": f'{file} records role "{me["role"]}", which is not in {taxonomy.path};'
                                       f" the login's role is used instead"}
    return {"role": me["role"], "file": file}


def find_taxonomy(_from: str | None = None) -> str | None:
    """agent-fabric's identities/roles/catalog.json, under the fabric root."""
    f = os.path.join(paths.fabric_root(), "identities", "roles", "catalog.json")
    return f if os.path.exists(f) else None


def slug_of(instance: str, taxonomy: Taxonomy) -> str | None:
    """The longest slug an instance name carries as a whole run of
    hyphen-separated tokens (`architect-cto-01`; a generic `user` names
    none). A convenience for a TO-ROLE match when no binding records a role
    and for a disagreement warning — never identity, never a reason to
    reject."""
    tokens = instance.split("-")
    best = None
    for slug in taxonomy.roles:
        st = slug.split("-")
        for i in range(len(tokens) - len(st) + 1):
            if tokens[i:i + len(st)] == st and (best is None or len(slug) > len(best)):
                best = slug
    return best


RELAY_MAX_COLUMNS = 72   # the width a terminal copy keeps; not the bridge's
_SWALLOWED = re.compile(f"[{JS_SPACE}]*[A-Z][A-Z0-9-]*:[{JS_SPACE}]*")


def validate(text: str, taxonomy: Taxonomy | None = None, max_columns: int = RELAY_MAX_COLUMNS,
             t: i18n.Printer | None = None) -> dict:
    """{ok, errors, warnings, message} — the Node's result shape."""
    t = t or en()
    errors: list[str] = []
    warnings: list[str] = []
    # parse() raises on a bad header because nothing after it can be read;
    # validate() reports that like any other error, one line, uniform shape.
    try:
        msg = parse(text, t)
    except NotGzcoord as e:
        return {"ok": False, "errors": [str(e)], "warnings": warnings, "message": None}
    meta, sections = msg["metadata"], msg["sections"]
    # SPEC §8, §18: a retired type is named as retired, not as unknown — an
    # unknown type would send it looking for a typo.
    if msg["type"] in RETIRED_TYPES:
        errors.append(t("validate.retired-type", {"type": msg["type"]}))
    elif msg["type"] not in CORE_TYPES and not msg["type"].startswith("X-"):
        errors.append(t("validate.unknown-type", {"type": msg["type"]}))
    # MESSAGE-ID joined the required set (§7.1) once a real transport made
    # its absence expensive. Uniqueness stays a SENDER obligation.
    for key in ("FROM", "ROLE", "PROJECT", "MESSAGE-ID"):
        if not meta.get(key):
            errors.append(t("validate.missing", {"key": key}))
    if meta.get("FROM") and not ADDRESS.fullmatch(meta["FROM"]):
        errors.append(t("validate.from-shape"))
    if meta.get("TO") and not ADDRESS.fullmatch(meta["TO"]):
        errors.append(t("validate.to-shape"))
    if "REPLY-EXPECTED" in meta and meta["REPLY-EXPECTED"] not in ("yes", "no"):
        errors.append(t("validate.reply-expected"))
    # SPEC §7.1: BROADCAST's only value is `true`.
    if "BROADCAST" in meta and meta["BROADCAST"] != "true":
        errors.append(t("validate.broadcast-value"))
    # SPEC §7.1: exactly one addressing field — a transport filtering by
    # addressee cannot obey two.
    addressing = [k for k in ("TO", "TO-ROLE", "BROADCAST") if k in meta]
    if not addressing:
        errors.append(t("validate.no-addressing"))
    elif len(addressing) > 1:
        errors.append(t("validate.addressing-exclusive", {"fields": " and ".join(addressing)}))
    # SPEC §13: an assignment — a REQUEST, or anything carrying a REQUEST:,
    # ACCEPTANCE: or DELIVER-TO: section — goes TO one instance; a role's
    # holders each execute it unaware of the others (2026-09-19: two PRs on
    # one hunk). Sections by their marker: a REQUEST: line meant as prose
    # still counts — that is the shape that misrouted.
    if "TO-ROLE" in meta:
        asks = [k for k in ("REQUEST", "ACCEPTANCE", "DELIVER-TO") if k in sections]
        if msg["type"] == "REQUEST":
            errors.append(t("validate.request-to-role"))
        elif asks:
            # Each key literally beside its t(: the i18n suite's
            # dead-and-missing guard reads the source for them.
            errors.append(t("validate.sections-to-role", {"sections": " and ".join(asks)}) if len(asks) > 1
                          else t("validate.section-to-role", {"sections": " and ".join(asks)}))
    for key in meta:
        if key in FORBIDDEN:
            errors.append(t("validate.forbidden-key", {"key": key}))
    if taxonomy is not None:
        catalogue = taxonomy.path or "the role catalogue"
        if meta.get("ROLE") and meta["ROLE"] not in taxonomy.roles:
            errors.append(t("validate.role-unknown", {"role": meta["ROLE"], "catalogue": catalogue}))
        if meta.get("TO-ROLE") and meta["TO-ROLE"] not in taxonomy.roles:
            errors.append(t("validate.to-role-unknown", {"role": meta["TO-ROLE"], "catalogue": catalogue}))
        from_slug = (slug_of(meta["FROM"].split("/")[1], taxonomy)
                     if meta.get("FROM") and ADDRESS.fullmatch(meta["FROM"]) else None)
        if from_slug and meta.get("ROLE") and meta["ROLE"] in taxonomy.roles and meta["ROLE"] != from_slug:
            warnings.append(t("validate.role-drift", {"from_slug": from_slug, "role": meta["ROLE"]}))
    for line in msg["malformed"]:
        errors.append(t("validate.unparsable-line", {"line": line}))
    for key in msg["duplicateKeys"]:
        errors.append(t("validate.duplicate-key", {"key": key}))
    # A key the sender believed was a known field: a misspelling of one, or
    # an id-shaped value under a key that is not an id field. Neither rejects.
    for key, value in meta.items():
        near = nearest_known_key(key)
        if near:
            warnings.append(t("validate.near-key", {"key": key, "near": near}))
        elif ID_SHAPED.fullmatch(value) and key not in ("MESSAGE-ID", "IN-REPLY-TO"):
            warnings.append(t("validate.id-shaped", {"key": key, "value": value}))
    # The converse: an id field whose value is not id-shaped — a warning,
    # because §7.2 keeps the id opaque; the sender turns it into a refusal.
    for key in ("MESSAGE-ID", "IN-REPLY-TO"):
        c = id_complaint(key, meta[key], t) if meta.get(key) else None
        if c:
            warnings.append(c)
    # A body line marker-shaped up to whitespace is body text by SPEC §6,
    # and also the exact shape a paste-indented section marker takes: the
    # message validates while the section folds into the one before it.
    # Warn, naming the line; never reclassify it.
    for name, body in sections.items():
        for line in body.split("\n"):
            if _SWALLOWED.fullmatch(line):
                warnings.append(t("validate.swallowed-marker", {"name": name, "line": json.dumps(line, ensure_ascii=False)}))
    # The same padding in the metadata block turns a marker into an
    # empty-valued key, and the body after it is reported as unparsable.
    for key, value in meta.items():
        if value == "":
            warnings.append(t("validate.empty-value", {"key": key}))
    # Not a grammar rule (SPEC §14 keeps carrier limits off the wire), but a
    # terminal copy re-breaks a long line and a re-broken metadata line
    # stops being metadata. The bridge carries a line as written, so send
    # passes max_columns 0; the CLI keeps it for a message someone will
    # paste. Columns, not code units.
    if max_columns > 0:
        body = text[1:] if text.startswith("﻿") else text
        for i, line in enumerate(re.split(r"\r?\n", body)):
            w = columns(line)
            if w > max_columns:
                warnings.append(t("validate.wide-line", {"n": i + 1, "width": w, "max": max_columns}))
    return {"ok": not errors, "errors": errors, "warnings": warnings, "message": msg}


def normalize(text: str) -> str:
    """Undo what a terminal copy does to a message, and nothing more
    (HUMAN-RELAY-TRANSPORT.md, "Receiving"). The metadata block — every
    line up to and including the first section marker — loses its leading
    whitespace unconditionally: the grammar admits no indented content
    there. That block is also where the carrier's indentation can be read:
    the most common leading whitespace across its KEY: value lines (ties to
    the shorter) is what the paste added, and exactly that prefix comes off
    each later line that begins with it. Every other body line is left
    alone: indentation inside a body is content. A paste that indented
    nothing returns the body byte for byte."""
    lines = _lines(text)
    out: list[str] = []
    votes: dict[str, int] = {}
    i = 0
    while i < len(lines):
        stripped = js_lstrip(lines[i])
        out.append(stripped)
        if _MARKER.fullmatch(stripped):
            i += 1
            break
        if i > 0 and _KEY_LINE.match(stripped):
            ws = lines[i][:len(lines[i]) - len(stripped)]
            votes[ws] = votes.get(ws, 0) + 1
        i += 1
    prefix, best = "", 0
    for ws, n in votes.items():
        if n > best or (n == best and len(ws) < len(prefix)):
            prefix, best = ws, n
    out.extend(l[len(prefix):] if prefix and l.startswith(prefix) else l for l in lines[i:])
    return "\n".join(out)


def mint_id() -> str:
    """A UUIDv7 (RFC 9562): 48-bit milliseconds, version 7, RFC variant —
    time-ordered and unique with no shared counter. The counter this
    replaced was the subsystem's largest defect source (five incidents);
    SPEC §7.2 says "opaque identifier", so the format is the deployment's."""
    b = bytearray(secrets.token_bytes(16))
    b[0:6] = (time.time_ns() // 1_000_000).to_bytes(6, "big")
    b[6] = (b[6] & 0x0F) | 0x70
    b[8] = (b[8] & 0x3F) | 0x80
    h = b.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


# Every flag a command accepts, declared, so an unrecognised one is an error
# BEFORE any side effect rather than a silent no-op: a checkout predating
# --peek once accepted `next-id --peek` (the retired counter) in silence and
# took a number.
FLAGS = {
    "validate": {"valued": ["taxonomy"], "boolean": ["no-taxonomy"], "positional": 1},
    "normalize": {"valued": [], "boolean": [], "positional": 1},
    "new-id": {"valued": [], "boolean": [], "positional": 0},
}


class UsageError(ValueError):
    pass


def parse_args(argv: list[str], spec: dict) -> dict:
    flags: dict[str, Any] = {}
    positional: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if not a.startswith("--"):
            positional.append(a)
            i += 1
            continue
        name = a[2:]
        if name in spec["boolean"]:
            flags[name] = True
            i += 1
            continue
        if name in spec["valued"]:
            v = argv[i + 1] if i + 1 < len(argv) else None
            if v is None or v.startswith("--"):
                raise UsageError(f"--{name} needs a value")
            if name in flags:
                raise UsageError(f"--{name} given twice")
            flags[name] = v
            i += 2
            continue
        known = ", ".join(f"--{f}" for f in [*spec["valued"], *spec["boolean"]])
        raise UsageError(f"unknown flag {a}; this command takes {known or 'no flags'}")
    if len(positional) > spec["positional"]:
        raise UsageError(f"unexpected argument: {positional[spec['positional']]}")
    return {"flags": flags, "positional": positional}


USAGE = "usage: gzmsg.mjs validate <file> | normalize <file> | new-id   (--taxonomy <path> | --no-taxonomy)"


def _read(file: str) -> str:
    with open(file, encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else None
    args = {"flags": {}, "positional": []}
    if cmd in FLAGS:
        try:
            args = parse_args(argv[1:], FLAGS[cmd])
        except UsageError as e:
            print(f"gzmsg {cmd}: {e}", file=sys.stderr)
            return 2
    # The catalogue is agent-fabric's; --taxonomy names one explicitly,
    # --no-taxonomy validates the wire grammar alone. Loaded before the
    # command is looked at, as the Node did: a catalogue that does not load
    # ends any command.
    tax_path = None if args["flags"].get("no-taxonomy") else (args["flags"].get("taxonomy") or find_taxonomy())
    try:
        taxonomy = load_taxonomy(tax_path) if tax_path else None
        if cmd == "validate":
            if not args["positional"]:
                raise UsageError("usage: gzmsg.mjs validate <file>")
            result = validate(_read(args["positional"][0]), taxonomy=taxonomy, t=i18n.t_for(whoami()))
            for w in result["warnings"]:
                print(f"warning: {w}", file=sys.stderr)
            if not result["ok"]:
                print("\n".join(result["errors"]), file=sys.stderr)
                return 1
            print("valid GZCOORD/1 message")
            return 0
        if cmd == "normalize":
            if not args["positional"]:
                raise UsageError("usage: gzmsg.mjs normalize <file>")
            sys.stdout.write(normalize(_read(args["positional"][0])))
            return 0
        if cmd == "new-id":
            # (`next-id`, the counter-era name, is an unknown command since 2026-09-16.)
            print(mint_id())
            return 0
    except (OSError, ValueError) as e:
        print(f"gzmsg: {e}", file=sys.stderr)
        return 1
    print(USAGE, file=sys.stderr)
    return 2


def run(argv: list[str]) -> int:
    """The command, with a last resort: one line and exit 1 (the Node died
    of an uncaught exception with exit 1 and a stack trace)."""
    try:
        return main(argv)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001 — the contract's last resort
        print(f"gzmsg: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))

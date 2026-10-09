"""tools/fabric/control/sessions.py — what this account's sessions are doing,
told to the state channel when it changes (ADR-029 rule 16):
runtime/control/sessions.mjs in Python (ADR-040 Wave 8), unwired until
the cutover, with j5's rule for a session state that cannot be read.

The harness hook runtime/claude-code/hooks/session-state.py keeps
<state>/session-state.json: per session id, working, blocked or idle,
since when, and the session's `claude` process with its start time.
agentd reads it every STATE_POLL_MS and posts a `state` record on the
state channel when what it would say differs from what it last said,
and again every STATE_HEARTBEAT_MS, so a listener that starts late, or
missed a record while the relay was down, converges without asking.

A session whose process is gone is left out: a kill or a crash never
sends SessionEnd, and an entry that outlived its process would read as
a session forever idle. The start time tells a reused pid from the
session's own. An entry that records no process (the hook ran outside a
harness) is believed only within NO_PROCESS_FRESH_MS of its `since`, and
said once when it is left out: kept for good it would read as a live
session forever, and tools/fabric/resume.py, which counts sessions this
way, would refuse every activation of the account. The hook's file is
never rewritten here; the hook owns it.

What leaves the account is the session id, its state and since when,
the binding's role and project, its last session's id with whether its
transcript is here (resumable), and `waits_on`, the GZCoord message ids
this login's blocked jobs wait on (ADR-037 rule 8): no path, no process
id, no title, no job id.

AN UNREADABLE SESSION STATE (j5; fabric-coordinator INFO 01a11e4e, the
owner 2026-10-09; python-dev-02's contract, INFO 01a11e4c and
01a11e4e-f664): new behaviour, not Node's. read_sessions answers [] when
the file is absent (none), and None — unknown — when it is there but
cannot be read, parsed, or is not {"sessions": {...}}, as resume.py's
live_sessions reads it. While it is unknown the watcher posts NO state
record, and logs once when the file goes unreadable and once when it
reads again: a listener keeps the last good record and reads it unknown
at STATES_STALE_MS, never a wrong "no sessions" — and nothing a Node
reader cannot read. (Node's sessions.mjs read both as [] and posted it.)
Saying "unreadable" on the wire is new wire behaviour, and waits until
the Node is deleted (ADR-040 §7; fabric-coordinator REPLY 01a11ec9-b9e8,
2026-10-09): then it is its own change, with ctl's reader for it.

WHAT IS NOT NODE'S, beyond that: `since` is read as ECMAScript's own
date-time format (Date.parse's ISO form: a date, a time with its offset
or Z, a time without one in local time); the other strings V8's
Date.parse also guesses at are not a time here, so an entry with no
process and such a `since` is not believed — the direction that leaves
a session out. The state file's path is the caller's: Node's default was
upgrade.mjs's stateDir(), which is another port's.
"""
from __future__ import annotations

import datetime
import json
import math
import os
import re
import sys
import time
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from control import js  # noqa: E402

STATE_FILE = "session-state.json"
STATE_POLL_MS = 2000
STATE_HEARTBEAT_MS = 10 * 60 * 1000
# Two heartbeats: the window in which a listener still trusts a state
# record (ctl.mjs STATES_STALE_MS). resume.py's NO_PROCESS_FRESH_S is the same.
NO_PROCESS_FRESH_MS = 2 * STATE_HEARTBEAT_MS
STATES = ("working", "blocked", "idle")
# A GZCoord MESSAGE-ID (a UUID, as gzmsg mints it); tools/fabric/jobs.py
# stores waits_on only in this shape. The cap keeps a record a record.
MESSAGE_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")   # matched whole
WAITS_ON_MAX = 64
# The harness's session id is a UUID; anything else in a binding is no
# session, never a path. resume.py's SESSION_RE is the same pattern, matched
# whole there too.
SESSION_ID = re.compile(r"[A-Za-z0-9-]{8,64}")   # matched whole

# ASCII digits only: \d would take Arabic-Indic ones, which int() reads.
_ISO = re.compile(r"(?a)(?P<y>[+-]\d{6}|\d{4})(?:-(?P<mo>\d\d)(?:-(?P<d>\d\d))?)?"
                  r"(?:[Tt](?P<h>\d\d):(?P<mi>\d\d)(?::(?P<s>\d\d)(?:\.(?P<ms>\d+))?)?(?P<z>[Zz]|[+-]\d\d:\d\d)?)?")


def date_parse(text) -> float:
    """Date.parse(text) for ECMAScript's date-time format, in ms; NaN for
    anything else (see WHAT IS NOT NODE'S)."""
    if not isinstance(text, str):
        return math.nan
    m = _ISO.fullmatch(text)
    if not m or m["y"] == "-000000":
        return math.nan
    year, month, day = int(m["y"]), int(m["mo"] or 1), int(m["d"] or 1)
    hour, minute, sec = int(m["h"] or 0), int(m["mi"] or 0), int(m["s"] or 0)
    ms = int((m["ms"] or "0")[:3].ljust(3, "0"))
    # A day past its month's end is V8's next month's (MakeDay), as 2026-02-29 is 1 March.
    if not (1 <= month <= 12 and 1 <= day <= 31 and minute <= 59 and sec <= 59
            and (hour <= 23 or (hour == 24 and minute == sec == ms == 0))):
        return math.nan
    t = ((_days_from_civil(year, month, 1) + day - 1) * 24 + hour) * 60 + minute
    t = t * 60_000 + sec * 1000 + ms
    if m["z"] is None and m["h"] is not None:
        return _time_clip(_local_to_utc(t))
    if m["z"] in (None, "Z", "z"):
        return _time_clip(t)       # a date alone is UTC; so is Z
    oh, om = int(m["z"][1:3]), int(m["z"][4:6])
    if oh > 23 or om > 59:
        return math.nan
    return _time_clip(t - (1 if m["z"][0] == "+" else -1) * (oh * 60 + om) * 60_000)


def _time_clip(t: int) -> float:
    """TimeClip: a time more than 8.64e15 ms from the epoch is NaN."""
    return float(t) if abs(t) <= 8.64e15 else math.nan


def _local_to_utc(t: int) -> int:
    """A local wall time (ms) as UTC, as ECMAScript reads it: of the
    instants that show it, the earliest (an hour that happens twice is its
    first); one that never happens (a clock moved forward) is read with the
    offset before the change."""
    offsets = {time.localtime((t - o * 1000) / 1000).tm_gmtoff for o in
               {time.localtime(t / 1000 + d).tm_gmtoff for d in (-86400, -3600, 0, 3600, 86400)}}
    shows = [t - o * 1000 for o in offsets if time.localtime((t - o * 1000) / 1000).tm_gmtoff == o]
    if shows:
        return min(shows)
    before = time.localtime(t / 1000 - 86400).tm_gmtoff
    return t - before * 1000


def _days_from_civil(y: int, m: int, d: int) -> int:
    y -= m <= 2
    era = y // 400       # floor already: the C algorithm's (y - 399) / 400 truncates
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _is_integer(v) -> bool:
    """Number.isInteger(v) on a JSON value: 5.0 is one, true is not, and
    neither is a number past the largest double (Infinity in JavaScript)."""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return False
    try:
        return float(v).is_integer()
    except OverflowError:
        return False


def fresh_without_process(since, now_ms: float) -> bool:
    """Whether an entry that records no process is still believed: within
    NO_PROCESS_FRESH_MS of its `since`. A `since` that is not a time is not."""
    t = date_parse(since if isinstance(since, str) else "")
    return math.isfinite(t) and now_ms - t <= NO_PROCESS_FRESH_MS


def alive(pid, start, proc: str = "/proc", *, since=None, now_ms: float | None = None) -> bool:
    """Whether the process the hook recorded is still the session's own."""
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    if not _is_integer(pid):
        return fresh_without_process(since, now_ms)
    try:
        with open(os.path.join(proc, str(int(pid)), "stat"), encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return False
    rest = raw[raw.rfind(")") + 2:].split(" ")
    if not _is_integer(start):
        return True
    field = js.number(rest[19]) if len(rest) > 19 else math.nan
    return field == start


def read_sessions(file: str, *, proc: str = "/proc", now_ms: float | None = None,
                  on_stale: Callable[[str], None] = lambda _id: None) -> list | None:
    """The sessions the file names whose process lives, sorted by id; [] when
    there is no file; None when it is there but cannot be read, parsed, or
    is not {"sessions": {...}} — unknown, never none (j5). on_stale(id) for
    each entry left out because it records no process and is stale."""
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    try:
        with open(file, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError):
        return None
    try:
        doc = js.json_parse(text)
    except ValueError:
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("sessions"), dict):
        return None
    out = []
    for sid, s in doc["sessions"].items():
        if not isinstance(s, dict) or s.get("state") not in STATES or not isinstance(s.get("state"), str):
            continue
        if alive(s.get("pid"), s.get("start"), proc, since=s.get("since"), now_ms=now_ms):
            since = s.get("since")
            out.append({"session": sid, "state": s["state"], "since": js.string("" if since is None else since)})
        elif not _is_integer(s.get("pid")):
            on_stale(sid)
    # JavaScript's < on strings: UTF-16 code units.
    return sorted(out, key=lambda r: r["session"].encode("utf-16-be", "surrogatepass"))


def waits_on(file: str | None) -> list | None:
    """The message ids this login's blocked jobs wait on, sorted, from its job
    list (agents/<login>/jobs.json, only read here). No list waits on
    nothing; a list that cannot be read is None — unknown, which the
    watcher never says as "nothing"."""
    if not file:
        return []
    try:
        with open(file, encoding="utf-8") as fh:
            doc = js.json_parse(fh.read())
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), list):
        return None
    ids = [j["waits_on"] for j in doc["jobs"] if isinstance(j, dict) and j.get("state") == "blocked"
           and isinstance(j.get("waits_on"), str) and MESSAGE_ID.fullmatch(j["waits_on"])]
    return sorted(set(ids))[:WAITS_ON_MAX]


def state_record(address: str, said: dict, ts: str | None = None) -> dict:
    """A State envelope (control/protocol.py)."""
    ts = js.iso_now() if ts is None else ts
    rec = {"v": 1, "kind": "state", "from": address, "ts": ts, "sessions": said["sessions"]}
    if js.truthy(said.get("role")):
        rec["role"] = said["role"]
    if js.truthy(said.get("project")):
        rec["project"] = said["project"]
    if js.truthy(said.get("last_session")):
        rec["last_session"] = said["last_session"]
        rec["resumable"] = said.get("resumable") is True
    if said.get("waits_on"):
        rec["waits_on"] = said["waits_on"]
    return rec


def transcript_exists(sid, config_dir: str | None = None) -> bool:
    """Whether a session's transcript is on this account: the file
    ~/.claude/projects/<launch dir>/<id>.jsonl that fabric-resume would hand
    to --resume. Which directory is not said; only that one exists."""
    if not isinstance(sid, str) or not SESSION_ID.fullmatch(sid):
        return False
    config_dir = config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    projects = os.path.join(config_dir, "projects")
    try:
        dirs = os.listdir(projects)
    except OSError:
        return False
    return any(os.path.exists(os.path.join(projects, d, f"{sid}.jsonl")) for d in dirs)


def _bound(file: str, config_dir: str | None) -> dict:
    try:
        with open(file, encoding="utf-8") as fh:
            b = js.json_parse(fh.read())
        sid = b.get("session") if isinstance(b, dict) else None
        sid = sid if isinstance(sid, str) and SESSION_ID.fullmatch(sid) else None
        return {"role": b.get("role"), "project": b.get("project"), "last_session": sid,
                "resumable": transcript_exists(sid, config_dir) if sid else False}
    except (OSError, UnicodeDecodeError, ValueError, AttributeError):
        return {"role": None, "project": None, "last_session": None, "resumable": False}


class StateWatcher:
    """tick() never raises and never runs twice at once. A post that fails
    leaves the last record unchanged, so the next tick tries again; it is
    said once, not every two seconds. `post` is called and its return is
    not awaited: an asynchronous caller passes a post that completes (or
    raises) before it returns."""

    def __init__(self, *, address: str, post: Callable[[dict], object], file: str, binding: str | None = None,
                 jobs: str | None = None, proc: str = "/proc", now: Callable[[], float] = lambda: time.time() * 1000,
                 heartbeat_ms: float = STATE_HEARTBEAT_MS, log: Callable[[str], None] = lambda m: print(m, file=sys.stderr),
                 config_dir: str | None = None):
        self.address, self.post, self.file, self.binding, self.jobs = address, post, file, binding, jobs
        self.proc, self.now, self.heartbeat_ms, self.log, self.config_dir = proc, now, heartbeat_ms, log, config_dir
        self.last_key, self.last_at, self.busy, self.failing = None, 0.0, False, False
        self.last_waits: list = []
        self.jobs_unreadable = False
        self.sessions_unreadable = False
        self.said_stale: set = set()

    def _on_stale(self, sid: str) -> None:
        if sid in self.said_stale:
            return
        self.said_stale.add(sid)
        self.log(f"agentd: session {sid} records no process and its state is older than "
                 f"{js.string(NO_PROCESS_FRESH_MS / 60000)} min; left out")

    def _waits_now(self) -> list:
        # An unreadable list keeps what was last said, and is said once:
        # identity.py replaces the file whole, so this is a broken file, not
        # a torn write.
        w = waits_on(self.jobs)
        if w is None:
            if not self.jobs_unreadable:
                self.log(f"agentd: the job list {self.jobs} cannot be read; waits_on kept as last said")
            self.jobs_unreadable = True
            return self.last_waits
        if self.jobs_unreadable:
            self.log("agentd: the job list is readable again")
            self.jobs_unreadable = False
        self.last_waits = w
        return w

    def _sessions_now(self, now_ms: float):
        s = read_sessions(self.file, proc=self.proc, now_ms=now_ms, on_stale=self._on_stale)
        if s is None:
            if not self.sessions_unreadable:
                self.log(f"{self.file} cannot be read; no state posted until it reads again")
            self.sessions_unreadable = True
            # The listener's record goes stale meanwhile: the first readable
            # tick posts at once, whether or not anything changed.
            self.last_key = None
            return None
        if self.sessions_unreadable:
            self.log(f"{self.file} is readable again")
            self.sessions_unreadable = False
        return s

    def tick(self) -> bool:
        if self.busy:
            return False
        self.busy = True
        try:
            now_ms = self.now()
            sessions = self._sessions_now(now_ms)
            if sessions is None:
                # Unknown: nothing is said, and the last record stands, to go
                # stale at the listener; the next readable tick posts.
                return False
            said = {"sessions": sessions,
                    **(_bound(self.binding, self.config_dir) if self.binding else
                       {"role": None, "project": None, "last_session": None, "resumable": False}),
                    "waits_on": self._waits_now()}
            key = json.dumps(said, sort_keys=False, ensure_ascii=True)
            if key == self.last_key and now_ms - self.last_at < self.heartbeat_ms:
                return False
            # new Date(now).toISOString(): whole milliseconds, truncated —
            # fromtimestamp() of a float rounds, a second ahead near a boundary.
            whole = int(now_ms)
            ts = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(milliseconds=whole)
            self.post(state_record(self.address, said, ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{whole % 1000:03d}Z"))
            self.last_key, self.last_at = key, now_ms
            if self.failing:
                self.log("agentd: session state posted again")
                self.failing = False
            return True
        except Exception as e:  # noqa: BLE001 — sessions.mjs's tick never throws: any failure is retried, said once
            if not self.failing:
                self.log(f"agentd: session state not posted ({e}); retrying")
                self.failing = True
            return False
        finally:
            self.busy = False

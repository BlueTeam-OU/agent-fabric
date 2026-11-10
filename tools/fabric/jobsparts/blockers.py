"""tools/fabric/jobsparts/blockers.py — checkable blockers: a blocked job that says what it waits on in a form the
tool can check, so it learns by itself that the wait is over. A part of tools/fabric/jobs.py, whose docstring is the
contract.

THE FORMS (`block <id> --on <blocker>`, several allowed, all must clear)
  pr:<owner/repo>#<n>       cleared when the pull request is merged or closed (gh, through tools/fabric/gh.py)
  request:<message-id>      answered when an inbound message of any type (a DECISION as well as a REPLY) whose
                            non-empty IN-REPLY-TO is that id is in this login's journal, as settle.py reads
                            the outbound side
                            (episodic.open_readonly, the one reader's door). A REPLY answers the request, it does
                            not deliver the work, so the answer is read first for the job the request became on the
                            answerer's board (the message's sender; through PEER READS below, as job: reads it): a row
                            whose title ends "(REQUEST <id>)" (records.request_id_of), the board being authoritative.
                            Only without a readable board is the body read (a board that says there is no such row
                            is a board read: the wait is over): exactly one job of the sender,
                            as job:<login>/j<n> or a bare j<n>, is the candidate (two or more: none), taken when
                            the board lists it or could not be read. Found: the stored blocker is replaced by
                            job:<login>/j<n> under the list's lock (the new spec starts with seen_open when the
                            board showed it), the job stays blocked, and the listings say once
                            "request:<id> answered; now waiting on job:<login>/j<n>". Not found (a decline, a
                            DECISION, a job closed or never on the board): cleared. The board unreadable and no
                            body match: unknown, never cleared. The re-pointed job then follows job: as below.
                            A re-point that would make a cycle is refused, said and never stored: the job it would
                            wait on is blocked on a job of this login that holds this blocker (CYCLES below).
  job:<login>/j<n>          cleared when that job is delivered, or has left the open list because it is done or
                            dropped; read as PEER READS below says
  clock:<YYYY-MM-DDTHH:MM[:SS]Z>
                            cleared once now() >= that UTC time (the Z is required: an offset or a bare local time is
                            refused). Stored as clock:YYYY-MM-DDTHH:MM:SSZ. `block` refuses a time already past (a
                            time that has gone by is no wait); an imported job may carry one, and it reads cleared.

PEER READS. `fabric-ctl <login> jobs` is a host operator's op: peers see each other's presence, not each other's lists.
So a caller that is a host operator reads the peer's board through it, as before; every other placed login asks the
peer's control agent the public op `job-state` (tools/fabric/control/jobs.py, through control/queue.py), which answers
one job's state to the sender of the request that job was taken from, and nothing else. Its answer: delivered, done
and dropped clear a job: blocker; any other state waits; "absent" (no such job on the list) clears only a job seen open
before, as an absent row of the board does; a refusal (the job is not one this login's request became) is unknown, with
the refusal's words. When the op cannot be asked at all (the registry, the relay, the interpreter), the caller reads the
board as before, so a failure is what fabric-ctl says of it, never a quiet default.

CYCLES. A re-point onto a job that waits on one of this login's jobs holding the same request: blocker would leave both
waiting for each other for ever. It is refused where it can be seen: when the target job is on this login's own list,
by following job: blockers on it; when it is on a peer's board this login can read (an operator), by that row's own
blockers. A peer's board the caller cannot read is not seen, and the public op will not say (it carries no blockers):
the cycle is then the other side's to find from the blocker it holds.

A CHECK says one of three things: `cleared`, `waiting`, or `unknown` (it could not be told: gh, the journal or
fabric-ctl failed, or the job is not on the open list and was never seen there). Unknown never clears a job.

THE CACHE (<state dir>/jobs-blockers.json, 0600): a listing checks at most once per CACHE_TTL_S per blocker; `start` (and
`switch <id>`, the same R4 need) decides on a fresh check (refresh(decide=True)), since a refusal read from a ten-minute-old "waiting" is wrong;
a cleared blocker stays cleared, since a merge, a reply and a delivered job do not undo. `--stored` and `--cached`
read it and check nothing. A job blocker also remembers that it was seen open: a job that is no longer on the open
list was closed only if it was seen open before; one never seen is unknown (a typo reads the same).
A clock blocker reads nothing but now(), so it is evaluated on every refresh: the TTL does not apply, and `--stored` and
`--cached` evaluate it too (the control plane sees it clear at the time). It never says unknown; once cleared it is
cached cleared like the others.
"""
from __future__ import annotations

import contextlib
import datetime
import fcntl
import json
import math
import os
import re
import sqlite3
import subprocess
import time
from typing import Any, Callable, NamedTuple
from fabric_jobs.base import FABRIC_ROOT, MESSAGE_ID, Refused, STATES, _load, identity, mutate, request_id_of
from fabric_jobs.queue import Unreachable, ask_queue

CACHE_TTL_S = 600
CTL_TIMEOUT_S = 30
_REPO = r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+"
PR = re.compile(rf"pr:({_REPO})#([1-9][0-9]{{0,8}})", re.ASCII)
REQUEST = re.compile(rf"request:({MESSAGE_ID.pattern})", re.ASCII)
JOB = re.compile(r"job:([a-z0-9][a-z0-9_-]{0,63})/(j[1-9][0-9]{0,8})", re.ASCII)
CLOCK = re.compile(r"clock:([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?Z", re.ASCII)
# What a free-text blocker names that has a checkable form: a PR number, or a GZCoord MESSAGE-ID.
NAMES_PR = re.compile(r"(?:\bPR\s*#?|#)\d+\b", re.IGNORECASE)
NAMES_MESSAGE = re.compile(MESSAGE_ID.pattern)
FORMS = "pr:<owner/repo>#<n>, request:<message-id>, job:<login>/j<n> or clock:<YYYY-MM-DDTHH:MM[:SS]Z> (UTC)"


class Check(NamedTuple):
    state: str          # "cleared", "waiting" or "unknown"
    detail: str
    became: str | None = None      # a request blocker only: the job:<login>/j<n> the answered request turned into
    became_seen: bool = False      # ...and whether it was found on that login's board (so it has been seen open)


# The clock, replaceable: the cache bound is tested without waiting.
now: Callable[[], float] = time.time


def _clock_time(m: re.Match[str]) -> datetime.datetime | None:
    """The UTC time a clock match names, None for a date or time that does not exist (2026-02-30, 24:00, second 60)."""
    year, month, day, hour, minute, second = (int(g or 0) for g in m.groups())
    try:
        return datetime.datetime(year, month, day, hour, minute, second, tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def clock_epoch(spec: str) -> float | None:
    """The time a normalised clock spec names, as epoch seconds; None when `spec` is not a clock spec."""
    m = CLOCK.fullmatch(spec)
    when = _clock_time(m) if m else None
    return when.timestamp() if when else None


def normalise(spec: str) -> str:
    """The blocker as it is stored, or Refused for a form that is none of the four."""
    text = spec.strip()
    if (m := CLOCK.fullmatch(text)):
        when = _clock_time(m)
        if when is None:
            raise Refused(f"{spec!r} names a time that does not exist: clock:<YYYY-MM-DDTHH:MM[:SS]Z> (UTC)")
        return f"clock:{when.year:04d}-{when:%m-%dT%H:%M:%S}Z"     # %Y alone does not pad a year below 1000 on glibc
    if text.startswith("clock:"):
        raise Refused(f"{spec!r} is not a UTC time: clock:<YYYY-MM-DDTHH:MM[:SS]Z>, with the trailing Z (an offset or a local time is refused)")
    if PR.fullmatch(text) or JOB.fullmatch(text):
        return text
    if REQUEST.fullmatch(text.lower()):
        return text.lower()
    raise Refused(f"{spec!r} is not a checkable blocker: {FORMS}; an owner's decision goes in the text "
                  "(fabric-jobs block <id> \"owner: <the decision awaited>\")")


def names_a_checkable(text: str) -> bool:
    return bool(NAMES_PR.search(text) or NAMES_MESSAGE.search(text))


# ── the checks ────────────────────────────────────────────────────────────────────────────────────────────

def check_pr(repo: str, number: str) -> Check:
    gh = _load("fabric_gh", os.path.join(FABRIC_ROOT, "tools", "fabric", "gh.py"))
    try:
        state = str(gh.pr_view(int(number), ["state"], repo=repo).get("state") or "")
    except gh.GhError as e:
        return Check("unknown", f"gh: {e.reason}"[:160])
    except (ValueError, TypeError):
        return Check("unknown", "gh answered something that is not a pull request state")
    if state in ("MERGED", "CLOSED"):
        return Check("cleared", state.lower())
    return Check("waiting", state.lower() or "no state")


BARE_JOB = re.compile(r"(?<![A-Za-z0-9_])(j[1-9][0-9]{0,8})(?![A-Za-z0-9_])", re.ASCII)
LOGIN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}", re.ASCII)


def _login_of(sender: object) -> str | None:
    """The login of a `<host>/<login>` address; None for anything else."""
    login = sender.rsplit("/", 1)[-1] if isinstance(sender, str) else ""
    return login if LOGIN.fullmatch(login) else None


def _jobs_named(body: str, login: str) -> set[str]:
    """The jobs of `login` a message body names: job:<login>/j<n>, or a bare j<n>. A job:<other>/j<n> names someone
    else's job and its j<n> is not the sender's."""
    mine = {m.group(2) for m in JOB.finditer(body) if m.group(1) == login}
    return mine | {m.group(1) for m in BARE_JOB.finditer(JOB.sub(" ", body))}


def _title_request(title: str) -> str | None:
    """records.request_id_of, the id folded to lower case as normalise stores a blocker's."""
    return request_id_of(re.sub(r"[0-9A-Fa-f-]{36}\)\Z", lambda m: m.group(0).lower(), " ".join(title.split())))


def ask_state(login: str, what: str) -> tuple[str, Any]:
    """The public op `job-state` asked of `login`'s control agent about `what` (a job id, or a message id): ("answer", the
    agent's answer), ("operator", None) when this login is a host operator and reads the board instead, or ("unreadable",
    why) when it could not be asked."""
    try:
        said = ask_queue("job-state", login, what)
    except Unreachable as e:
        return "unreadable", f"job-state: {e}"[:160]
    if said.get("operator") is True:
        return "operator", None
    answer = said.get("answer")
    if not isinstance(answer, dict):
        return "unreadable", "job-state: the answer is not one"
    return "answer", answer


def _refusal(answer: dict) -> str:
    return f"{answer.get('status')}: {answer.get('reason')}"[:160] if answer.get("status") == "refused" else \
        f"job-state: status {str(answer.get('status'))[:40]}"


def _spec_names(blockers: object) -> list[str]:
    """The specs of a board row's `blockers` (dicts with a spec, as fabric-jobs lists them) as text."""
    named = [b.get("spec") if isinstance(b, dict) else b for b in blockers] if isinstance(blockers, list) else []
    return [n for n in named if isinstance(n, str)]


def _became(mid: str, login: str, body: str, decision: bool = False) -> tuple[str | None, bool, str | None, list[str]]:
    """(the job the request became, whether the board showed it, why the board could not be read, the specs that job
    waits on where the board showed them). The board is the authority: a row whose title ends "(REQUEST <mid>)". Only
    without a readable board is the body read: a token there is taken when the board lists that job, or could not be
    read at all."""
    kind, got = ask_state(login, mid)
    if kind == "answer":
        # The control agent's own answer to "which job of yours did this request become": the state of that job, never its
        # title or its list, so the body is never asked to name it.
        if got.get("status") == "ok" and got.get("state") == "absent":
            return None, False, None, []
        if got.get("status") == "ok" and isinstance(got.get("id"), str) and got.get("state") in STATES \
                and JOB.fullmatch(f"job:{login}/{got['id']}"):
            return f"job:{login}/{got['id']}", True, None, []
        board, why = None, _refusal(got)
        # The body below is read only where the board could not be: a refusal is that.
    elif kind == "unreadable" or kind == "operator":
        board, why = read_board(login)
    rows = board or []
    if board is not None:
        for j in board:
            if _title_request(str(j.get("title", ""))) == mid and isinstance(j.get("id"), str) \
                    and JOB.fullmatch(f"job:{login}/{j['id']}"):      # a board row is another agent's text: only the job: form is stored
                return f"job:{login}/{j['id']}", True, None, _spec_names(j.get("blockers"))
    if decision:
        return None, False, None, []        # a DECISION settles the question, it is not a job taken: no body token, no unknown
    named = _jobs_named(body, login)
    if len(named) != 1:
        return None, False, why, []
    (job_id,) = named
    if board is None:
        return f"job:{login}/{job_id}", False, why, []
    # A readable board without that job: closed, or not the sender's work for this request, and the wait is over.
    row = next((j for j in rows if isinstance(j, dict) and j.get("id") == job_id), None)
    return (f"job:{login}/{job_id}", True, None, _spec_names(row.get("blockers"))) if row is not None else (None, False, None, [])


def _cycle(became: str, request: str, peer_specs: list[str]) -> str | None:
    """The job of this login that holds `request:<request>` and that `became` already waits on, or None (see CYCLES in
    the header). `peer_specs` are what a board this login could read shows the target waiting on."""
    me = identity.current_agent()
    doc = identity.read_jobs()
    holders = {f"job:{me}/{j['id']}" for j in doc["jobs"] if isinstance(j.get("id"), str) and f"request:{request}" in specs_of(j)}
    login, _, job_id = became[len("job:"):].partition("/")
    if login != me:
        return next((h for h in holders if h in peer_specs), None)
    # On this login's own list the walk is whole: the target, then what it waits on there.
    own = {f"job:{me}/{j['id']}": specs_of(j) for j in doc["jobs"] if isinstance(j.get("id"), str)}
    seen: set[str] = set()
    todo = [became]
    while todo:
        at = todo.pop()
        if at in holders:
            return at
        if at not in seen:
            seen.add(at)
            todo.extend(s for s in own.get(at, []) if s.startswith("job:"))
    return None


def check_request(message_id: str) -> Check:
    episodic = _load("fabric_episodic", os.path.join(FABRIC_ROOT, "tools", "fabric", "episodic.py"))
    path = episodic.db_path()
    if not os.path.exists(path):
        return Check("waiting", "no journal yet: nothing has been received")
    try:
        conn = episodic.open_readonly(path)
    except (episodic.JournalError, sqlite3.Error, OSError) as e:      # a file SQLite cannot open is not a JournalError
        return Check("unknown", f"journal: {e}"[:160])
    try:
        # lower(): the id is stored as the sender wrote it, the blocker as normalise() made it.
        # Any type: a DECISION answers a REQUEST as a REPLY does, and settle.py counts an outbound answer the same way (a DECISION is told
        # apart below only in whether it can leave the answer unknown). The id is
        # never empty, so an empty IN-REPLY-TO matches nothing.
        rows = conn.execute("SELECT sender, content, type FROM episodes WHERE direction='inbound' AND lower(in_reply_to)=? "
                            "ORDER BY happened_at, recorded_at, id", (message_id,)).fetchall()
    except Exception as e:  # noqa: BLE001 — an unreadable journal is unknown, never a traceback in a listing
        return Check("unknown", f"journal: {e}"[:160])
    finally:
        conn.close()
    if not rows:
        return Check("waiting", "no reply yet")
    # A REPLY answers the request, it does not deliver the work: when the answerer made a job of it, the wait is that job.
    unreadable, decided = None, False
    for sender, content, kind in rows:
        login = _login_of(sender)
        if login is None:
            continue
        body = str(content or "").partition("\n\n")[2]
        decision = str(kind).upper() == "DECISION"
        decided = decided or decision
        job, seen, why, peer_specs = _became(message_id, login, body, decision)
        if job:
            loop = _cycle(job, message_id, peer_specs)
            if loop:
                return Check("unknown", f"answered, but {job} waits on {loop}, which waits on this request: not re-pointed (a cycle)"[:160])
            return Check("waiting", f"answered; now waiting on {job}", job, seen)
        unreadable = unreadable or why
    if unreadable and not decided:      # a DECISION settles the question whatever an earlier unreadable answer left open
        # We cannot tell a "taken" from a "no": a clear we cannot justify hands the job back with nothing delivered.
        return Check("unknown", f"answered, but whether it became a job is not known: {unreadable}"[:160])
    return Check("cleared", "answered")


def check_clock(epoch: float) -> Check:
    """Reads now() and nothing else, so it is never unknown."""
    when = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
    stamp = f"{when.year:04d}-{when:%m-%dT%H:%M:%S}Z"
    left = epoch - now()
    if left <= 0:
        return Check("cleared", f"reached {stamp}")
    minutes = math.ceil(left / 60)
    return Check("waiting", f"until {stamp}, in {minutes // 60}h{minutes % 60}m")


def ctl_program() -> list[str]:
    return [os.environ.get("AGENT_FABRIC_CTL") or os.path.join(FABRIC_ROOT, "bin", "fabric-ctl")]


def read_board(login: str) -> tuple[list[dict] | None, str]:
    """(`login`'s open list as fabric-ctl gives it, ""), or (None, why it could not be read)."""
    try:
        p = subprocess.run([*ctl_program(), login, "jobs", "--json", "--timeout", "20"], capture_output=True, text=True,
                           timeout=CTL_TIMEOUT_S, stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        return None, f"fabric-ctl did not answer within {CTL_TIMEOUT_S} s"
    except OSError as e:
        return None, f"fabric-ctl could not run ({e.strerror or e})"
    row = None
    for text in p.stdout.splitlines():
        try:
            doc = json.loads(text)
        except ValueError:
            continue
        if isinstance(doc, dict) and doc.get("account") == login:
            row = doc
    if row is None or row.get("status") != "ok":
        why = (p.stderr.strip().splitlines() or [f"{login}: no answer" if row is None else f"{login}: {row.get('status')}"])[-1]
        return None, f"fabric-ctl: {why}"
    listed = (row.get("jobs") or {}).get("jobs") if isinstance(row.get("jobs"), dict) else None
    if not isinstance(listed, list):
        return None, f"fabric-ctl: {login} gave no list of jobs"
    return [j for j in listed if isinstance(j, dict)], ""


def check_job(login: str, job_id: str, seen_open: bool) -> tuple[Check, bool]:
    """(the check, whether the job has now been seen on the open list). Absent from the open list is done or
    dropped only for a job seen open before."""
    kind, got = ask_state(login, job_id)
    if kind == "answer":
        return _from_answer(login, job_id, got, seen_open)
    board, why = read_board(login)
    if board is None:
        return Check("unknown", why[:160]), seen_open
    job = next((j for j in board if j.get("id") == job_id), None)
    if job is None:
        return _absent(login, job_id, seen_open)
    if job.get("state") == "delivered":
        return Check("cleared", "delivered"), True
    return Check("waiting", str(job.get("state") or "open")), True


def _absent(login: str, job_id: str, seen_open: bool) -> tuple[Check, bool]:
    if seen_open:
        return Check("cleared", "closed (done or dropped)"), True
    return Check("unknown", f"{job_id} is not on {login}'s open list: no such job, or closed before it was seen"), False


def _from_answer(login: str, job_id: str, answer: dict, seen_open: bool) -> tuple[Check, bool]:
    """A check from the public op's answer. done and dropped are on the list the op reads (it reads --all), so they
    clear whether or not the job was seen open; only a job gone from it altogether needs the sighting."""
    state = answer.get("state")
    if answer.get("status") != "ok":
        return Check("unknown", f"{login}'s control agent: {_refusal(answer)}"[:160]), seen_open
    if answer.get("id") not in (job_id, None) or not isinstance(state, str) or (state not in STATES and state != "absent"):
        return Check("unknown", f"{login}'s control agent answered something that is not a state of {job_id}"), seen_open
    if state == "absent":
        return _absent(login, job_id, seen_open)
    if state == "delivered":
        return Check("cleared", "delivered"), True
    if state in ("done", "dropped"):
        return Check("cleared", "closed (done or dropped)"), True
    return Check("waiting", state), True


# ── the cache ───────────────────────────────────────────────────────────────────────────────────────────────────

def cache_path() -> str:
    return os.path.join(identity.agent_state_dir(), "jobs-blockers.json")


def _sane(entry: dict) -> dict:
    """A cache entry as it is trusted: a state of the three, a `checked_at` that is a finite time no later than a
    minute from now (a value out of range, or from a clock that was ahead, would otherwise stop a recheck or crash
    the listing that formats it), and the `seen_open` memory."""
    at = entry.get("checked_at")
    out = {k: entry[k] for k in ("detail", "seen_open") if k in entry}
    if isinstance(entry.get("became"), str) and JOB.fullmatch(entry["became"]):
        out["became"] = entry["became"]
    if entry.get("state") in ("cleared", "waiting", "unknown"):
        out["state"] = entry["state"]
    if isinstance(at, (int, float)) and not isinstance(at, bool) and math.isfinite(at) and 0 <= at <= now() + 60:
        out["checked_at"] = at
    return out


def load_cache() -> dict[str, dict]:
    try:
        with open(cache_path(), encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return {}
    return {k: _sane(v) for k, v in doc.items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(doc, dict) else {}


def save_cache(cache: dict[str, dict]) -> None:
    path = cache_path()
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        identity.atomic_write(path, json.dumps(cache, indent=1), 0o600)
    except OSError:
        pass   # a cache that cannot be written is checked again next time; it never fails a listing


@contextlib.contextmanager
def _locked():
    """The cache's read-modify-write, one process at a time. Held only around that merge: a check (gh, the journal,
    fabric-ctl) is made before it, never inside it."""
    try:
        os.makedirs(os.path.dirname(cache_path()), mode=0o700, exist_ok=True)
        fd = os.open(cache_path() + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        yield     # no lock to be had: the last writer wins, as it would have without one
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def forget(specs: list[str]) -> None:
    """Start `specs` over: a job that blocks again on a spec gets a fresh check, not the answer a former wait left (a
    cleared blocker stays cleared only for as long as the wait it belonged to). What was SEEN stays: another job may be
    blocked on the same spec, and a job that left the peer's open list was closed only if it was seen open."""
    with _locked():
        cache = load_cache()
        changed = False
        for spec in dict.fromkeys(specs):
            entry = cache.pop(spec, None)
            if entry is not None:
                changed = True
                if entry.get("seen_open"):
                    cache[spec] = {"seen_open": True}
        if changed:
            save_cache(cache)


def run_check(spec: str, entry: dict | None) -> dict:
    """The cache entry for `spec`, freshly checked."""
    seen = bool((entry or {}).get("seen_open"))
    became, became_seen = None, False
    try:
        m = PR.fullmatch(spec)
        if m:
            result = check_pr(m.group(1), m.group(2))
        elif (m := REQUEST.fullmatch(spec)):
            result = check_request(m.group(1))
            became, became_seen = result.became, result.became_seen
        elif (m := JOB.fullmatch(spec)):
            result, seen = check_job(m.group(1), m.group(2), seen)
        elif (epoch := clock_epoch(spec)) is not None:
            result = check_clock(epoch)
        else:
            result = Check("unknown", "not a checkable form")
    except Exception as e:  # noqa: BLE001 — a check can fail in ways nobody listed (gh not executable, an answer of another shape): unknown, never a dead listing
        result = Check("unknown", f"the check failed: {type(e).__name__}: {e}"[:160])
    return {"state": result.state, "detail": result.detail, "checked_at": now(), **({"seen_open": True} if seen else {}),
            # `became_seen` is private to refresh(), which turns it into the new spec's own cache entry
            **({"became": became, "became_seen": became_seen} if became else {})}


def refresh(specs: list[str], *, check: bool = True, decide: bool = False) -> dict[str, dict]:
    """The cache entry of each spec. With `check`, one that is not cleared and was last checked more than CACHE_TTL_S
    ago (or never) is checked now; a cleared one is never checked again. With `decide` (needs.py's start, which refuses on a
    blocker that waits) the TTL does not hold a check back: a refusal read from a `waiting` entry up to ten minutes old
    keeps a job blocked after its peer was delivered. Without `check`, nothing is checked, except a clock
    spec, which is evaluated either way. The checks run
    first and the results are merged into the file under the lock, keeping a `cleared` another process wrote and the
    `seen_open` either has."""
    cache = load_cache()
    fresh: dict[str, dict] = {}
    for spec in dict.fromkeys(specs):
        entry = cache.get(spec)
        if clock_epoch(spec) is not None:
            # Free to evaluate and decided by the clock alone: neither `check=False` nor the TTL holds it back.
            if not (entry and entry.get("state") == "cleared"):
                fresh[spec] = run_check(spec, entry)
            continue
        if not check or (entry and (entry.get("state") == "cleared"
                                    or (not decide and isinstance(entry.get("checked_at"), (int, float))
                                        and now() - entry["checked_at"] < CACHE_TTL_S))):
            continue
        fresh[spec] = run_check(spec, entry)
    # A re-point that could not be written last time is made again by the next look.
    # Only a look that checks writes: --stored, --cached and show are reads (the control agent's op, a hook).
    repointed: dict[str, str] = {s: cache[s]["became"] for s in specs if check and (cache.get(s) or {}).get("became")}
    if fresh:
        with _locked():
            cache = load_cache()
            for spec, new in fresh.items():
                old = cache.get(spec) or {}
                if old.get("state") == "cleared":
                    continue
                if old.get("seen_open"):
                    new["seen_open"] = True
                if (became := new.get("became")) and new.pop("became_seen", False):
                    cache[became] = {**(cache.get(became) or {}), "seen_open": True}
                new.pop("became_seen", None)
                if became:
                    repointed[spec] = became
                cache[spec] = new
            save_cache(cache)
    for spec, became in repointed.items():
        repoint_blocker(spec, became)
    return {s: cache[s] for s in specs if s in cache}


def repoint_blocker(spec: str, became: str) -> None:
    """Replace the stored blocker `spec` (a request) by `became` (the job it turned into) in every blocked job that holds
    it, under the list's lock. The job stays blocked: a REPLY answers the request, the work is delivered by the job. Never
    called inside that lock: refresh() runs before any verb's mutate."""
    mid = spec.split(":", 1)[1]

    def edit(doc: dict) -> None:
        for job in doc["jobs"]:
            if spec not in specs_of(job):      # leaving blocked drops the blockers, so this is a blocked job
                continue
            job["blockers"] = list(dict.fromkeys(became if s == spec else s for s in specs_of(job)))
            if job.get("waits_on") == mid:
                job.pop("waits_on")      # the state stream ranks the job that request asked for; this one is answered
            on = str(job.get("blocked_on") or "")
            job["blocked_on"] = on.replace(spec, became).replace(f"request {mid}", became) if mid in on else on
            job["updated"] = identity.now_iso()
            job.setdefault("log", []).append({"at": job["updated"], "kind": "repoint",       # no `state`: not a transition
                                              "note": f"{spec} answered; now waiting on {became}"})
    try:
        mutate(edit)
    except (OSError, Refused):
        pass    # the cache says what was found; the job is re-pointed by the next look


# ── what a job says of its blockers ─────────────────────────────────────────────────────────────────────────────

def specs_of(job: dict) -> list[str]:
    value = job.get("blockers")
    return [s for s in value if isinstance(s, str)] if isinstance(value, list) else []


def states_of(job: dict, cache: dict[str, dict]) -> list[dict[str, Any]]:
    """[{"spec", "state", "detail"?, "checked_at"}] for a job's checkable blockers, from `cache` alone. A spec never
    checked is `unknown` with a null time."""
    out = []
    for spec in specs_of(job):
        e = cache.get(spec) or {}
        at = e.get("checked_at")
        try:
            when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at)) if isinstance(at, (int, float)) else None
        except (OverflowError, ValueError, OSError):
            when = None
        out.append({"spec": spec, "state": e.get("state") if e.get("state") in ("cleared", "waiting", "unknown") else "unknown",
                    "detail": e.get("detail"), "checked_at": when, **({"became": e["became"]} if e.get("became") else {})})
    return out


def cleared_flag(job: dict, cache: dict[str, dict]) -> bool | None:
    """True when every checkable blocker is cleared, False when one was checked and still waits, None when the job
    has none, or none has been told yet (all unknown)."""
    states = [s["state"] for s in states_of(job, cache)]
    if not states:
        return None
    if all(s == "cleared" for s in states):
        return True
    if any(s == "waiting" for s in states):
        return False
    return None


def all_specs(doc: dict, *, only_blocked: bool = True) -> list[str]:
    return [s for j in doc["jobs"] if (j["state"] == "blocked" or not only_blocked) for s in specs_of(j)]

"""tools/fabric/control/deaf.py — a session that went idle with no inbox watch, said from outside it (j188).

WHY. An idle session has no turn in which to arm its watch again, so a watch ended by something outside the session leaves
it deaf until a person looks: the carrier's give-ups of 11-15 and 11-18 (exit 5) and the harness reaping 16 idle watches under
memory pressure on 11-21, five of which sat deaf for 25 h (docs/live-checks/2026-11-22-carrier-give-up-waves-and-idle-deafness.md,
"What this decides"). The hooks that re-arm run inside the session; this is the reader that does not.

THE RULE, per account, read by that account's control agent (the `deaf` section of `status`, and the op `deaf`):
  deaf  <=>  a session runs
         and the last line of gzcoord-watch.jsonl is an `end` (any code), or a `start` while no process of this login is a
             watch (inbox-watch.is_watch, the predicate the Stop hook and session-start ask)
         and that has held for more than MIN_AGE_S, counted from the line's own time, or from the session's start when the
             session is newer than the line (a session that has just begun has not yet had its first turn to arm one)
         and the account has work waiting: a queued job whose title ends "(REQUEST <id>)", or, where the reader counts the
             account's own spool (the carrier's), an unread message.
         The job is the REQUEST's marker, whatever its source: a deaf session never runs the receiver half of intake (that runs in
         its own watch, source "request"); the sender half (gzcoord/intake.py queue_for_addressee) files it through the jobs-add op
         as source "owner", and only when the sender is the addressee's host operator. A REQUEST from anyone else, to a session in
         a relay mode, leaves no job and no own-spool count; the relay's reading is channel-wide, so when it shows unread messages
         and no REQUEST job is queued the section answers UNKNOWN (cannot tell whether any is this account's), never "no work".

A start line followed by no end is also what a watch killed outright leaves (a SIGKILL, the reap), so "no live watch" is read
from the process table, never from the log alone; a start while a watch process lives is a live watch.

WHAT IS NOT KNOWN IS NOT DECIDED. A log that cannot be read, a process table that cannot be read, or a section (presence,
inbox, jobs) that failed answers {"status": "unknown", "reason"}, never "not deaf". An account with no log line at all, or with
no session, or with no waiting work, answers deaf False with the reason in `why`. The relay's cursor reader counts every message of the project channel past the account's cursor, others' traffic included (drift.py),
and with no watch the cursor stops, so there "unread" would be true of any busy channel: it is not counted as work, and the alarm says
only what was counted. Only the carrier's own-spool reading (its `source` is the carrier's name) counts unread messages.

IDLE (j1061). A deaf account is restarted by deaf_alarm.py only when its session is idle, which the section says as `idle`
true | false | "unknown" with `idle_why`, read from the session's own transcript (the binding's session id, ~/.claude/projects/*/<id>.jsonl):
idle <=> the transcript has had no write for MIN_AGE_S AND its last assistant record ended its turn (stop_reason end_turn) AND no tool_use
is left without a tool_result. A pending tool_use is NOT idle: that is a session held at a permission prompt or inside a long foreground
call, and a restart would throw its pending work away (rust-ui-dev-02, 2026-11-27 16:58Z, held at the dispatch guard's prompt). A transcript
that cannot be found or read, or has no assistant record, is "unknown", never idle.

The episode: `episode` is the watch-log line's own event and time, which does not change between polls, so the alarm
(deaf_alarm.py) sends one message for it and not one per poll; a new `end` or `start` line, or a recovery, is a new episode.
"""
from __future__ import annotations

import datetime
import glob
import importlib.util
import json
import os
import time
from typing import Any, Callable, Mapping

MIN_AGE_S = 600
# The log is a bounded jsonl of short lines; the last event is in its tail.
TAIL_BYTES = 64 * 1024
WATCH_LOG = "gzcoord-watch.jsonl"
# One message of a transcript can be a whole file read; the last turn's records are in the tail, not the head.
TRANSCRIPT_TAIL_BYTES = 2 * 1024 * 1024
# An assistant turn that ended on its own. `tool_use` is the model waiting for a tool, a permission prompt or a long call.
ENDED_TURN = ("end_turn", "stop_sequence", "max_tokens", "refusal")


def last_watch_event(log: str) -> dict | None:
    """The newest `start` or `end` line of the watch log, or None when the file is absent or holds none. Raises OSError for a log
    that exists and cannot be read: that is unknown, not an account that never watched."""
    try:
        with open(log, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - TAIL_BYTES))
            tail = fh.read()
    except FileNotFoundError:
        return None
    for raw in reversed(tail.split(b"\n")):
        try:
            line = json.loads(raw)
        except ValueError:
            continue   # a torn first line of the tail, or a torn last one from a crash
        if isinstance(line, dict) and line.get("event") in ("start", "end") and isinstance(line.get("t"), str):
            return line
    return None


def parse_t(stamp: str) -> float | None:
    try:
        d = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.timestamp() if d.tzinfo else None


def live_watch(uid: int, is_watch: Callable[[list[str]], bool], proc: str = "/proc") -> bool:
    """Whether a process of this login is an inbox watch. OSError when the table cannot be listed (unknown)."""
    for name in os.listdir(proc):
        if not name.isdigit():
            continue
        path = os.path.join(proc, name)
        try:
            if os.stat(path).st_uid != uid:
                continue
            with open(os.path.join(path, "cmdline"), "rb") as fh:
                argv = [a.decode("utf-8", "replace") for a in fh.read().split(b"\0") if a]
        except OSError:
            continue   # gone since the listing, or not ours
        if argv and is_watch(argv):
            return True
    return False


def load_is_watch(root: str) -> Callable[[list[str]], bool]:
    spec = importlib.util.spec_from_file_location("fabric_inbox_watch", os.path.join(root, "runtime", "claude-code", "hooks", "inbox-watch.py"))
    if spec is None or spec.loader is None:
        raise ImportError("no inbox-watch.py under " + root)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.is_watch


def transcript_path(session: str | None, home: str) -> str:
    """The running session's transcript. ValueError when the id or the file cannot be found: the caller says unknown."""
    # The id is a UUID and becomes a glob and a file name: anything else is refused, not matched.
    if not isinstance(session, str) or not session or not all(c.isalnum() or c == "-" for c in session):
        raise ValueError("the binding has no usable session id")
    found = glob.glob(os.path.join(glob.escape(home), ".claude", "projects", "*", session + ".jsonl"))
    if len(found) != 1:
        raise ValueError(f"{len(found)} transcripts of session {session} found")
    return found[0]


def read_tail(path: str) -> list[dict]:
    with open(path, "rb") as fh:
        size = fh.seek(0, os.SEEK_END)
        start = max(0, size - TRANSCRIPT_TAIL_BYTES)
        fh.seek(start)
        raw = fh.read()
    lines = raw.split(b"\n")
    if start:
        lines = lines[1:]   # the first line of a tail is cut
    out = []
    for ln in lines:
        try:
            rec = json.loads(ln)
        except ValueError:
            continue   # a torn last line from a write in progress
        if isinstance(rec, dict):
            out.append(rec)
    return out


def judge_transcript(records: list[dict]) -> tuple[bool | str, str]:
    """(idle, why) from a transcript's records: pure."""
    uses: set[str] = set()
    results: set[str] = set()
    last: dict | None = None
    for rec in records:
        msg = rec.get("message")
        if rec.get("type") not in ("user", "assistant") or not isinstance(msg, dict) or rec.get("isSidechain"):
            continue   # attachments, hook output and bookkeeping lines say nothing of the turn
        last = rec
        content = msg.get("content")
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use" and isinstance(block.get("id"), str):
                uses.add(block["id"])
            elif isinstance(block, dict) and block.get("type") == "tool_result" and isinstance(block.get("tool_use_id"), str):
                results.add(block["tool_use_id"])
    if last is None:
        return "unknown", "the transcript has no user or assistant record"
    if uses - results:
        return False, "a tool call is pending (held at a permission prompt or in a long call)"
    reason = last["message"].get("stop_reason")
    if reason in ENDED_TURN:
        return True, "the last assistant turn ended"
    # A user record (a prompt, or a tool result the model has not answered) has no stop_reason: it lands here too.
    if reason is None or reason == "tool_use":
        return False, "in a turn (the last record has not ended its turn)"
    return "unknown", f"the last assistant record's stop_reason is {str(reason)[:40]!r}"


def idle_of(session: Callable[[], str | None], home: str, now: float, min_age_s: int = MIN_AGE_S) -> tuple[bool | str, str]:
    try:
        path = transcript_path(session(), home)
        age = now - os.stat(path).st_mtime
        if age < min_age_s:
            return False, f"in a turn (the transcript was written {max(int(age), 0)} s ago)"
        return judge_transcript(read_tail(path))
    except (OSError, ValueError, ImportError) as e:   # ValueError: identity refused the binding, or the transcript is not one
        return "unknown", f"the transcript cannot be read ({e.__class__.__name__}: {str(e)[:120]})"


def _unknown(why: str) -> dict:
    return {"status": "unknown", "reason": why[:200]}


def _no(why: str, **more: Any) -> dict:
    return {"status": "ok", "deaf": False, "why": why, **more}


def pending_work(inbox: Callable[[], Any], jobs: Callable[[], Any]) -> tuple[dict | None, str | None]:
    """({"unread": n or None, "queued_requests": m}, None), or (None, why) when either reader does not say or raises. `unread` is
    None where the inbox reading is the relay's channel-wide one (not this account's own work)."""
    try:
        i = inbox()
    except Exception as e:  # noqa: BLE001 — a reader that raised said nothing: unknown, with its reason
        return None, f"inbox: {e.__class__.__name__}: {e}"
    try:
        j = jobs()
    except Exception as e:  # noqa: BLE001
        return None, f"jobs: {e.__class__.__name__}: {e}"
    if not isinstance(i, dict) or i.get("status") != "ok" or not isinstance(i.get("unread"), int):
        return None, f"inbox: {i.get('status') if isinstance(i, dict) else 'no answer'}"
    if not isinstance(j, dict) or j.get("status") != "ok" or not isinstance(j.get("jobs"), list):
        return None, f"jobs: {j.get('status') if isinstance(j, dict) else 'no answer'}"
    from control.jobs import _request_of   # the one reading of the title marker (job-state asks the same)
    queued = sum(1 for x in j["jobs"] if isinstance(x, dict) and x.get("state") == "queued" and _request_of(x.get("title")) is not None)
    from gzcoord.carrier import CARRIER_NAME   # position.section marks its own-spool reading with the carrier's name
    own = i.get("source") == CARRIER_NAME
    if not own and i["unread"] and not queued:
        return None, "inbox: the relay's unread count is channel-wide, so whether any message is this account's is not known"
    return {"unread": i["unread"] if own else None, "queued_requests": queued}, None


def judge(*, session: Any, last: dict | None, watching: bool | None, now: float, ask_pending: Callable[[], tuple[dict | None, str | None]],
          min_age_s: int = MIN_AGE_S, ask_idle: Callable[[], tuple[bool | str, str]] | None = None) -> dict:
    """The rule on what the account has said. `ask_pending` is asked only once everything before it says deaf: the inbox is a
    relay read and the jobs list a subprocess, and an account with a live watch pays for neither."""
    if not isinstance(session, dict) or session.get("status") != "ok":
        return _unknown(f"presence: {session.get('status') if isinstance(session, dict) else 'no answer'}")
    if not session.get("online"):
        return _no("no session runs")
    if last is None:
        return _no("no watch log line yet")
    t = parse_t(last["t"])
    if t is None:
        return _unknown("the watch log's last line has no readable time")
    since = parse_t(session["since"]) if isinstance(session.get("since"), str) else None
    if last["event"] == "start":
        if watching is None:
            return _unknown("the process table could not be read")
        if watching:
            return _no("a watch runs")
        how = f"start, no live watch (pid {last.get('pid')})"
    else:
        how = f"end code {last.get('code')}" + (f" ({last['reason']})" if isinstance(last.get("reason"), str) else "")
    # A session newer than the line has had no turn to arm one yet: the clock starts when it did.
    began = max(t, since) if since is not None else t
    age = int(now - began)
    if age <= min_age_s:
        return _no("deaf for less than the minimum", age_s=max(age, 0))
    pending, why = ask_pending()
    if pending is None:
        return _unknown(why or "pending work not read")
    if not pending["unread"] and not pending["queued_requests"]:   # None unread: not counted
        return _no("no work is waiting", age_s=age)
    # Asked last, like the inbox: only an account that is deaf has a transcript worth reading.
    idle, idle_why = ask_idle() if ask_idle else ("unknown", "no transcript reader")
    return {"status": "ok", "deaf": True, "watch": how, "age_s": age,
            "since": datetime.datetime.fromtimestamp(began, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "episode": f"{last['event']}@{last['t']}", "pending": pending, "idle": idle, "idle_why": idle_why}


def _binding_session() -> str | None:
    from control.ops import util
    return util.binding_session()


def section(ctx: Mapping[str, Any], *, presence: Callable[[], Any], inbox: Callable[[], Any], jobs: Callable[[], Any]) -> dict:
    """The `deaf` section. `presence`, `inbox` and `jobs` are the account's other sections, handed in so this module imports no op."""
    opts = ctx.get("deaf_opts") or {}
    now = opts.get("now", time.time())
    state = opts.get("state")
    if state is None:
        from control.ops import util
        state = util.state_dir()
    try:
        last = last_watch_event(os.path.join(state, WATCH_LOG))
    except OSError as e:
        return _unknown(f"the watch log cannot be read ({e.__class__.__name__})")
    watching: bool | None = None
    if last is not None and last["event"] == "start":
        try:
            is_watch = opts.get("is_watch") or load_is_watch(ctx.get("root") or opts["root"])
            watching = live_watch(opts.get("uid", os.getuid()), is_watch, opts.get("proc", "/proc"))
        except Exception:  # noqa: BLE001 — an unreadable command table or process table is unknown, never "no watch"
            watching = None
    return judge(session=presence(), last=last, watching=watching, now=now,
                 ask_pending=lambda: pending_work(inbox, jobs),
                 ask_idle=lambda: idle_of(opts.get("session") or _binding_session, opts.get("home") or os.path.expanduser("~"), now))

#!/usr/bin/env python3
"""Contract test of runtime/claude-code/hooks/plan-hold.sh, the hook whose
marker holds this account's GZCoord inbox while a session plans (Wave 9
batch 6; the oracle of the port, ADR-040 rule 5). The entry point is ENTRY,
run as the harness runs it: a program with the hook payload on stdin;
$PLAN_HOLD_HOOK aims the same test at its replacement. The reader side
(gzcoord-inbox --held) is tests/test_gzcoord_protocol.py and
tests/test_session_commands.py.

Every case of runtime/claude-code/hooks/test_plan-hold.sh:
  1 a default-mode tool call is silent; 2 no marker outside plan mode; 3 a
  plan-mode tool call is silent; 4 the marker appears on a plan-mode event;
  5 it names the harness pid, its /proc start time and the session; 6 the
  hold directory is 700; 7 a marker naming this pid is written once, not per
  event; 8 a default-mode prompt is silent; 9 the marker is gone after a
  non-plan event of the same session; 10 a plan-mode event with agent_id
  writes nothing; 11 a default-mode event with agent_id clears nothing; 12
  each of two planning sessions has its own marker; 13 the first stays held
  after the second released; 14 the second's marker is gone; 15 the second
  stays held after the first released; 16 a dead session's marker is swept;
  17 our own is kept; 18 a marker whose pid was reused (another start time)
  is swept; 19 a marker naming another login's process (pid 1) is swept; 20
  a marker naming no pid, or pid 0, is swept; 21 a symlinked hold directory
  gets nothing; 22 our own directory with a loose mode is tightened and
  used; 23 SessionEnd is silent; 24 and clears the session's own marker; 25
  malformed, 26 empty and 27 event-less input are silent; 28 and write
  nothing.
Added where a refactor could break the contract: stdout and stderr both
empty and exit 0 on every event; a marker written once keeps its inode and
mtime (no sleeps: the rewrite is what is compared); the marker is complete
JSON with an ISO `since`, and no temporary file is left beside it; the
session id is CLAUDE_CODE_SESSION_ID before the payload's; the harness is
CLAUDE_PID, else the hook's parent (this process); a CLAUDE_PID that is no
positive integer writes nothing; the default directory is
$HOME/.cache/agent-fabric/hold; a null agent_id is the session itself, a
non-empty one a subagent; SessionEnd of another session leaves a live
sibling's marker; no jq: silent exit 0, nothing written (with the control).

Mutations, each failing here: the `agent_id` early exit removed (10); `-L`
check removed (21); the sweep's `alive` accepting any pid (16, 18, 19, 20);
`[[ -f $marker ]] && exit 0` removed (7); the start-time comparison removed
(18); the SessionEnd branch treated as plan mode (24); `rm -f "$marker"`
removing every marker (13, 15); CLAUDE_CODE_SESSION_ID ignored (session case).

Exit codes: 0 all assertions passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys

import hook_harness as h

ENTRY = h.entry("PLAN_HOLD_HOOK", "plan-hold.sh")
T = h.sandbox("test_plan_hold_cli.")
HOME = os.path.join(T, "home")
DIR = os.path.join(T, "hold")
PID = os.getpid()
MARKER = os.path.join(DIR, f"{PID}.json")
t = h.Tests("plan hold")


def payload(event: str, mode: str | None, agent: str | None = None, session: str = "sess-1") -> str:
    # The shape the harness sends (2.1.273): session_id present, agent_id null for the session itself.
    doc: dict = {"hook_event_name": event, "session_id": session, "agent_id": None, "transcript_path": "/t", "cwd": "/"}
    if mode is not None:
        doc["permission_mode"] = mode
    if agent is not None:
        doc.update(agent_id=agent, agent_type="code-low")
    return json.dumps(doc)


def environment(pid: int | str = PID, session: str = "sess-1", **extra: str) -> dict[str, str]:
    return h.env(HOME, **{"AGENT_FABRIC_HOLD_DIR": DIR, "CLAUDE_PID": str(pid), "CLAUDE_CODE_SESSION_ID": session, **extra})


def fire(event: str, mode: str | None, agent: str | None = None, pid: int | str = PID, session: str = "sess-1") -> h.Result:
    return h.run(ENTRY, payload(event, mode, agent, session), environment(pid, session))


def silent(label: str, r: h.Result) -> None:
    t.check(label, r.rc == 0 and r.out == "" and r.err == "", f"rc={r.rc} out={r.out!r} err={r.err!r}")


def held(path: str = MARKER) -> bool:
    return os.path.isfile(path)


def marker_doc(path: str = MARKER) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def start_of(pid: int) -> str:
    with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
        return fh.read().rsplit(") ", 1)[1].split()[19]


def sleeper() -> subprocess.Popen:
    return subprocess.Popen(["sleep", "300"])


def write(path: str, doc: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)


def main() -> int:
    os.makedirs(HOME)
    t.group("the marker follows the permission mode")
    silent("a default-mode tool call is silent", fire("PreToolUse", "default"))
    t.check("no marker outside plan mode", not held())
    silent("a plan-mode tool call is silent", fire("PreToolUse", "plan"))
    t.check("the marker appears on a plan-mode event", held())
    doc = marker_doc()
    t.check("the marker names the harness pid, its start time and the session",
            doc.get("pid") == PID and doc.get("start") == start_of(PID) and doc.get("session_id") == "sess-1", str(doc))
    t.check("the marker's `since` is an ISO UTC time", re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", str(doc.get("since"))) is not None, str(doc))
    t.check("the hold directory is 700", stat.S_IMODE(os.stat(DIR).st_mode) == 0o700, oct(os.stat(DIR).st_mode))
    t.check("nothing but the marker is left in the directory", sorted(os.listdir(DIR)) == [f"{PID}.json"], str(os.listdir(DIR)))
    before = os.stat(MARKER)
    silent("a second plan-mode event is silent", fire("UserPromptSubmit", "plan"))
    after = os.stat(MARKER)
    t.check("a marker naming this pid is written once, not per event", (before.st_ino, before.st_mtime_ns) == (after.st_ino, after.st_mtime_ns))

    t.group("leaving plan mode clears it")
    silent("a default-mode prompt is silent", fire("UserPromptSubmit", "default"))
    t.check("the marker is gone after a non-plan event of the same session", not held())
    fire("PreToolUse", "plan")
    fire("PreToolUse", None)
    t.check("an event that carries no permission_mode is not planning", not held())

    t.group("a subagent's event is not the session's mode")
    fire("PreToolUse", "plan", "sub-1")
    t.check("a plan-mode event with agent_id writes nothing", not held())
    fire("PreToolUse", "plan")
    fire("PreToolUse", "default", "sub-1")
    t.check("a default-mode event with agent_id clears nothing", held())
    fire("SessionEnd", None, "sub-1")
    t.check("a subagent's SessionEnd clears nothing", held())

    t.group("two sessions under one login hold and release independently")
    with sleeper() as other:
        other_marker = os.path.join(DIR, f"{other.pid}.json")
        fire("PreToolUse", "plan", pid=other.pid, session="sess-2")
        t.check("each planning session has its own marker", held() and held(other_marker), str(os.listdir(DIR)))
        t.check("…and the second names its own session and start time",
                marker_doc(other_marker).get("session_id") == "sess-2" and marker_doc(other_marker).get("start") == start_of(other.pid), str(marker_doc(other_marker)))
        fire("UserPromptSubmit", "default", pid=other.pid, session="sess-2")
        t.check("the first session is still held after the second released", held())
        t.check("the second session's marker is gone", not held(other_marker))
        fire("PreToolUse", "plan", pid=other.pid, session="sess-2")
        fire("UserPromptSubmit", "default")
        t.check("the second session stays held after the first released", not held() and held(other_marker), str(os.listdir(DIR)))
        fire("PreToolUse", "plan")
        fire("SessionEnd", None, pid=other.pid, session="sess-2")
        t.check("a SessionEnd of the second leaves the first held", held() and not held(other_marker), str(os.listdir(DIR)))
        fire("PreToolUse", "plan", pid=other.pid, session="sess-2")
        other.kill()
        other.wait()
    fire("PreToolUse", "plan")
    t.check("a dead session's marker is swept by any event", not held(other_marker))
    t.check("our own is kept", held())

    t.group("a marker whose harness is not a live one of this login is swept")
    with sleeper() as reused:
        reused_marker = os.path.join(DIR, f"{reused.pid}.json")
        fire("PreToolUse", "plan", pid=reused.pid, session="sess-3")
        doc = marker_doc(reused_marker)
        write(reused_marker, json.dumps({**doc, "start": "1"}))
        fire("PreToolUse", "plan")
        t.check("a live pid with another start time is a reused pid: swept", not held(reused_marker))
        fire("PreToolUse", "plan", pid=reused.pid, session="sess-3")
        fire("PreToolUse", "plan")
        t.check("…and the same marker with its true start time is kept (the control)", held(reused_marker))
        reused.kill()
        reused.wait()
    write(os.path.join(DIR, "1.json"), '{"pid":1,"session_id":"forged","start":""}\n')
    fire("PreToolUse", "plan")
    t.check("a marker naming another login's process is swept", not held(os.path.join(DIR, "1.json")))
    write(os.path.join(DIR, "7.json"), '{"session_id":"nopid"}\n')
    write(os.path.join(DIR, "8.json"), '{"pid":0}\n')
    write(os.path.join(DIR, "9.json"), "not json")
    fire("PreToolUse", "plan")
    t.check("a marker naming no pid, or pid 0, or no JSON, is swept", not any(held(os.path.join(DIR, f"{n}.json")) for n in (7, 8, 9)), str(os.listdir(DIR)))

    t.group("the directory must be the login's own")
    fire("UserPromptSubmit", "default")
    shutil.rmtree(DIR)
    elsewhere = os.path.join(T, "elsewhere")
    os.makedirs(elsewhere)
    os.symlink(elsewhere, DIR)
    silent("a symlinked hold directory is silent", fire("PreToolUse", "plan"))
    t.check("a symlinked hold directory gets nothing", os.listdir(elsewhere) == [], str(os.listdir(elsewhere)))
    os.unlink(DIR)
    os.mkdir(DIR, 0o755)
    os.chmod(DIR, 0o755)
    fire("PreToolUse", "plan")
    t.check("our own directory with a loose mode is tightened and used", stat.S_IMODE(os.stat(DIR).st_mode) == 0o700 and held(), oct(os.stat(DIR).st_mode))
    shutil.rmtree(DIR)
    h_default = os.path.join(HOME, ".cache", "agent-fabric", "hold")
    h.run(ENTRY, payload("PreToolUse", "plan"), {k: v for k, v in environment().items() if k != "AGENT_FABRIC_HOLD_DIR"})
    t.check("the default directory is $HOME/.cache/agent-fabric/hold", held(os.path.join(h_default, f"{PID}.json")), str(os.listdir(HOME)))
    shutil.rmtree(os.path.join(HOME, ".cache"))

    t.group("the session and the harness it names")
    shutil.rmtree(DIR, ignore_errors=True)
    h.run(ENTRY, payload("PreToolUse", "plan", session="from-payload"), {k: v for k, v in environment().items() if k != "CLAUDE_CODE_SESSION_ID"})
    t.check("without CLAUDE_CODE_SESSION_ID the payload's session id is used", marker_doc().get("session_id") == "from-payload", str(marker_doc()))
    shutil.rmtree(DIR)
    h.run(ENTRY, payload("PreToolUse", "plan", session="from-payload"), environment(session="from-env"))
    t.check("CLAUDE_CODE_SESSION_ID wins over the payload's session id", marker_doc().get("session_id") == "from-env", str(marker_doc()))
    shutil.rmtree(DIR)
    h.run(ENTRY, payload("PreToolUse", "plan"), {k: v for k, v in environment().items() if k != "CLAUDE_PID"})
    t.check("without CLAUDE_PID the harness is the hook's parent, this process", marker_doc().get("pid") == PID, str(os.listdir(DIR)))
    shutil.rmtree(DIR)
    for bad in ("0", "-5", "12x", "abc"):
        silent(f"CLAUDE_PID {bad!r} is silent", fire("PreToolUse", "plan", pid=bad))
    t.check("CLAUDE_PID that is no positive integer writes nothing", not os.path.isdir(DIR) or os.listdir(DIR) == [], str(os.listdir(DIR) if os.path.isdir(DIR) else ""))

    t.group("SessionEnd clears the session's own marker")
    fire("PreToolUse", "plan")
    t.check("held", held())
    silent("SessionEnd is silent", fire("SessionEnd", None))
    t.check("cleared at session end", not held())
    fire("PreToolUse", "plan")
    fire("SessionEnd", "plan")
    t.check("SessionEnd clears even when it carries plan mode", not held())

    t.group("never loud")
    for label, text in (("malformed", "not json"), ("empty", ""), ("an event-less object", "{}")):
        silent(f"{label} input is silent", h.run(ENTRY, text, environment()))
    t.check("and writes nothing", not held())
    bare = h.tool_dir(os.path.join(T, "bare"), ["bash", "cat", "env"])
    shutil.rmtree(DIR, ignore_errors=True)
    r = h.run(ENTRY, payload("PreToolUse", "plan"), {**environment(), "PATH": bare})
    t.check("without jq: silent, exit 0, nothing written", r.rc == 0 and r.out == "" and not os.path.isdir(DIR), f"{r.rc} {r.out!r}")
    fire("PreToolUse", "plan")
    t.check("…and the same payload with jq holds (the control)", held())
    return t.finish()


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(T, ignore_errors=True)

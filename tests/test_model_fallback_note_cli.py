#!/usr/bin/env python3
"""Contract test of runtime/claude-code/hooks/model-fallback-note.sh, the
PostModelSwitch hook that tells a session its model fell back (Wave 9 batch
6; the oracle of the port, ADR-040 rule 5). The entry point is ENTRY, run as
the harness runs it: a program, the hook payload on stdin, $MODEL_FALLBACK_HOOK
to aim the same test at its replacement.

Every case of runtime/claude-code/hooks/test_model-fallback-note.sh:
  1 an automatic switch exits 0; 2 the note names both models; 3 names the
  flagged category read from the transcript; 4 asks to filter the category
  out of GZCoord messages, commits, PR bodies and memories; 5 says the switch
  is sticky (until /model) and asks to be reported; 6 the output names its
  event; 7 a marker names the harness pid, session, fallback model and
  category; 8 the marker directory is 700; 9 without a transcript the
  category is unnamed; 10 silent on sources command, picker, sdk, resume;
  11 silent on PreModelSwitch; 12 no marker written by any of them; 13 a dead
  session's marker is swept and ours written; 14 malformed input is silent;
  15 empty input is silent.
Added where a refactor could break the contract: the output shape (exactly
one hookSpecificOutput), stderr empty, the topic for a biology and for an
unlisted category, the LAST fallback line of a transcript decides, absent
models read "the launched model" / "a fallback model", the session id comes
from CLAUDE_CODE_SESSION_ID before the payload, the default marker directory
under $HOME, a marker for the pid when CLAUDE_PID is absent (the parent), no
marker but still the note for a bad CLAUDE_PID or a symlinked directory, a
loose-mode directory tightened, a live session's marker kept and an
unreadable one swept, nothing but the marker left in the directory, no jq:
silent exit 0 (with the positive control).

Mutations, each failing here: the source test `== "auto"` dropped (cases
10, 12); the sweep removed (13); the category read from the FIRST line
(last-line case); the chmod removed (loose mode);
the symlink check removed (symlinked directory); `[[ "$pid" =~ ... ]]`
removed (bad CLAUDE_PID); the sweep deleting live markers (live kept).

Exit codes: 0 all assertions passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys

import hook_harness as h

ENTRY = h.entry("MODEL_FALLBACK_HOOK", "model-fallback-note.sh")
T = h.sandbox("test_model_fallback_note_cli.")
HOME = os.path.join(T, "home")
DIR = os.path.join(T, "fallback")
PID = os.getpid()
MARKER = os.path.join(DIR, f"{PID}.json")
FALLBACK_LINE = {"type": "system", "subtype": "model_refusal_fallback", "trigger": "refusal", "scope": "session",
                 "originalModel": "claude-opus-5[1m]", "fallbackModel": "claude-opus-4-8", "apiRefusalCategory": "cyber"}
t = h.Tests("fallback note")


def transcript(name: str, *lines: dict) -> str:
    path = os.path.join(T, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(line) + "\n" for line in lines)
    return path


CYBER = transcript("cyber.jsonl", {"type": "user"}, FALLBACK_LINE, {"type": "assistant"})


def payload(event: str = "PostModelSwitch", source: str | None = "auto", **over) -> str:
    doc = {"hook_event_name": event, "session_id": "sess-1", "source": source, "from_model": "claude-opus-5[1m]",
           "to_model": "claude-opus-4-8", "requested_model": None, "cwd": "/", "transcript_path": CYBER, **over}
    return json.dumps({k: v for k, v in doc.items() if not (k == "source" and v is None)})


def environment(**extra: str) -> dict[str, str]:
    return h.env(HOME, **{"AGENT_FABRIC_FALLBACK_DIR": DIR, "CLAUDE_PID": str(PID), "CLAUDE_CODE_SESSION_ID": "sess-1", **extra})


def fire(text: str, **extra: str) -> h.Result:
    return h.run(ENTRY, text, environment(**extra))


def note_of(r: h.Result) -> str:
    try:
        return json.loads(r.out)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError, TypeError):
        return f"<no note: rc={r.rc} out={r.out!r}>"


def marker(path: str = MARKER) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def left() -> list[str]:
    return sorted(os.listdir(DIR)) if os.path.isdir(DIR) else []


def clear() -> None:
    shutil.rmtree(DIR, ignore_errors=True)


def main() -> int:
    os.makedirs(HOME)
    t.group("an automatic switch is announced to the session")
    r = fire(payload())
    ctx = note_of(r)
    t.check("exit 0", r.rc == 0, str(r.rc))
    t.check("stderr is empty", r.err == "", r.err)
    t.check("the note names both models", "claude-opus-5[1m]" in ctx and "claude-opus-4-8" in ctx, ctx)
    t.check("the note names the flagged category, read from the transcript", "flagged your last request as a cybersecurity issue" in ctx, ctx)
    t.check("the note asks to filter the category out of everything that follows",
            all(s in ctx for s in ("filter out of everything you send", "GZCoord messages, commit messages, PR bodies, memories",
                                   "anything that could be read as a cybersecurity issue", "never its content")), ctx)
    t.check("the note says the switch is sticky and asks for it to be reported", "until /model" in ctx and "Say in your next report" in ctx, ctx)
    out = json.loads(r.out) if r.out.strip() else {}
    t.check("the output names its event", out.get("hookSpecificOutput", {}).get("hookEventName") == "PostModelSwitch", r.out)
    t.check("the output is exactly one hookSpecificOutput with the event and the note",
            list(out) == ["hookSpecificOutput"] and sorted(out.get("hookSpecificOutput", {})) == ["additionalContext", "hookEventName"], r.out)
    m = marker() or {}
    t.check("a marker names the harness pid, the session, the fallback model and the category",
            m.get("pid") == PID and m.get("to_model") == "claude-opus-4-8" and m.get("session_id") == "sess-1" and m.get("category") == "cyber", str(m))
    t.check("the marker also names the origin model, the time and the topic",
            m.get("from_model") == "claude-opus-5[1m]" and m.get("topic") == "a cybersecurity issue" and str(m.get("at", "")).endswith("Z"), str(m))
    t.check("the marker directory is 700", stat.S_IMODE(os.stat(DIR).st_mode) == 0o700, oct(os.stat(DIR).st_mode))
    t.check("nothing but the marker is left in the directory", sorted(os.listdir(DIR)) == [f"{PID}.json"], str(os.listdir(DIR)))
    ctx = note_of(fire(payload(transcript_path="/nonexistent")))
    t.check("without a transcript the category is unnamed", "as the category the safeguard flagged" in ctx, ctx)

    t.group("the topic follows the category the transcript names")
    for category, want in (("biosecurity", "a biology or biosecurity issue"), ("cyber_harm", "a cybersecurity issue"), ("weapons", "a weapons issue")):
        path = transcript(f"{category}.jsonl", {**FALLBACK_LINE, "apiRefusalCategory": category})
        ctx = note_of(fire(payload(transcript_path=path)))
        t.check(f"category {category}: {want}", f"flagged your last request as {want}" in ctx, ctx)
    first_cyber = transcript("two.jsonl", FALLBACK_LINE, {"type": "assistant"}, {**FALLBACK_LINE, "apiRefusalCategory": "bio"})
    ctx = note_of(fire(payload(transcript_path=first_cyber)))
    t.check("the LAST fallback line is this switch", "a biology or biosecurity issue" in ctx and "cybersecurity" not in ctx, ctx)
    ctx = note_of(fire(payload(from_model=None, to_model=None)))
    t.check("models the payload omits read as the launched and a fallback model", "from the launched model to a fallback model" in ctx, ctx)

    t.group("the marker follows the session's own identity")
    clear()
    fire(payload(session_id="from-payload"), CLAUDE_CODE_SESSION_ID="from-env")
    t.check("the session id is CLAUDE_CODE_SESSION_ID before the payload's", (marker() or {}).get("session_id") == "from-env", str(marker()))
    clear()
    # Neither CLAUDE_CODE_SESSION_ID nor CLAUDE_PID: the payload names the session, the hook's parent (this process) the harness.
    bare_env = {k: v for k, v in environment().items() if k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_PID")}
    h.run(ENTRY, payload(session_id="from-payload"), bare_env)
    t.check("without it the payload's session id is used", (marker() or {}).get("session_id") == "from-payload", str(marker()))
    t.check("a harness whose CLAUDE_PID is absent is the hook's parent, this process", (marker() or {}).get("pid") == PID,
            str(left()))
    clear()
    r = fire(payload(), CLAUDE_PID="not-a-pid")
    t.check("a CLAUDE_PID that is no pid: the note, and no marker", "flagged your last request" in note_of(r) and left() == [], r.out)
    clear()
    r = fire(payload(), CLAUDE_PID="0")
    t.check("CLAUDE_PID 0 (would signal the group): the note, and no marker", "flagged your last request" in note_of(r) and left() == [], r.out)
    clear()
    default_dir = os.path.join(HOME, ".cache", "agent-fabric", "fallback")
    h.run(ENTRY, payload(), {k: v for k, v in environment().items() if k != "AGENT_FABRIC_FALLBACK_DIR"})
    t.check("the default marker directory is under $HOME/.cache/agent-fabric/fallback", marker(os.path.join(default_dir, f"{PID}.json")) is not None, str(os.listdir(HOME)))
    shutil.rmtree(os.path.join(HOME, ".cache"), ignore_errors=True)

    t.group("the marker directory must be the login's own")
    clear()
    elsewhere = os.path.join(T, "elsewhere")
    os.makedirs(elsewhere)
    os.symlink(elsewhere, DIR)
    r = fire(payload())
    t.check("a symlinked directory gets no marker, and the note is still given", os.listdir(elsewhere) == [] and "flagged your last request" in note_of(r), str(os.listdir(elsewhere)))
    os.unlink(DIR)
    os.mkdir(DIR, 0o755)
    os.chmod(DIR, 0o755)
    fire(payload())
    t.check("our own directory with a loose mode is tightened and used", stat.S_IMODE(os.stat(DIR).st_mode) == 0o700 and marker() is not None, oct(os.stat(DIR).st_mode))

    t.group("silent on every switch the session asked for")
    clear()
    for src in ("command", "picker", "sdk", "resume"):
        r = fire(payload(source=src))
        t.check(f"PostModelSwitch {src}: nothing", r.rc == 0 and r.out == "" and r.err == "", f"{r.rc} {r.out!r}")
    r = fire(payload(source=None))
    t.check("PostModelSwitch with no source: nothing", r.rc == 0 and r.out == "", r.out)
    r = fire(payload(event="PreModelSwitch"))
    t.check("PreModelSwitch: nothing (the harness never sends auto there)", r.rc == 0 and r.out == "", r.out)
    r = fire(payload(event="SessionStart"))
    t.check("any other event: nothing", r.rc == 0 and r.out == "", r.out)
    t.check("no marker written by any of them", left() == [], str(left()))

    t.group("a dead session's marker is swept")
    os.makedirs(DIR, exist_ok=True)
    os.chmod(DIR, 0o700)
    with open(os.path.join(DIR, "4194304000.json"), "w", encoding="utf-8") as fh:
        fh.write('{"pid":4194304000,"session_id":"gone"}\n')
    with open(os.path.join(DIR, "junk.json"), "w", encoding="utf-8") as fh:
        fh.write("not json")
    with subprocess.Popen(["sleep", "300"]) as live:
        with open(os.path.join(DIR, f"{live.pid}.json"), "w", encoding="utf-8") as fh:
            json.dump({"pid": live.pid, "session_id": "other"}, fh)
        fire(payload())
        t.check("dead swept, ours written", not os.path.exists(os.path.join(DIR, "4194304000.json")) and marker() is not None, str(os.listdir(DIR)))
        t.check("a marker that is no JSON is swept", not os.path.exists(os.path.join(DIR, "junk.json")), str(os.listdir(DIR)))
        t.check("a live session's marker is kept", os.path.exists(os.path.join(DIR, f"{live.pid}.json")), str(os.listdir(DIR)))
        live.kill()

    t.group("never loud")
    for label, text in (("malformed", "not json"), ("empty", ""), ("an empty object", "{}")):
        r = fire(text)
        t.check(f"{label} input is silent", r.rc == 0 and r.out == "", f"{r.rc} {r.out!r} {r.err!r}")
    bare = h.tool_dir(os.path.join(T, "bare"), ["bash", "cat", "env"])
    clear()
    r = h.run(ENTRY, payload(), {**environment(), "PATH": bare})
    t.check("without jq: silent, exit 0, nothing written", r.rc == 0 and r.out == "" and not os.path.isdir(DIR), f"{r.rc} {r.out!r}")
    t.check("…and the same payload with jq speaks (the control)", "flagged your last request" in note_of(fire(payload())))
    return t.finish()


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(T, ignore_errors=True)

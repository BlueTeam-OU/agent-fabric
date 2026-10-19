#!/usr/bin/env python3
"""tools/fabric/model_fallback_note.py — the Claude Code PostModelSwitch hook that tells a session its model fell
back, behind runtime/claude-code/hooks/model-fallback-note.sh (Wave 9 batch 6, ADR-040 §5). The reasons are
agent-fabric ADR-007; the contract is pinned by tests/test_model_fallback_note_cli.py.

Contract, frozen from the shell script:
  stdin   the hook payload: hook_event_name, source, from_model, to_model, session_id, transcript_path. Empty,
          malformed or not-an-object input does nothing
  act     only on PostModelSwitch with source "auto" (a switch the harness made itself); every other event or
          source, a resume included, is silent
  env     CLAUDE_PID (the harness; the hook's parent when unset or empty), CLAUDE_CODE_SESSION_ID (before the
          payload's session_id), AGENT_FABRIC_FALLBACK_DIR (else $HOME/.cache/agent-fabric/fallback)
  stdout  one hookSpecificOutput whose additionalContext is the note; nothing otherwise. Nothing on stderr
  exit    0 always: a PostModelSwitch hook cannot block, and this one is a note, not a guard, so a hook that
          cannot run is "no note", as the shell script was without jq
  writes  <dir>/<pid>.json (700 directory, ours, not a symlink; else the note alone) naming the session, the
          models, the time and the category, for gzcoord-send and fabric-status; markers of harnesses that are
          gone are swept

The flagged category is not in the hook input: the transcript records the fallback as a model_refusal_fallback
line with apiRefusalCategory, and the last such line is this switch.
"""
import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import plan_hold  # noqa: E402 — the marker directory, sweep and liveness rules are the plan-hold marker's: one implementation

FALLBACK_TOKEN = b'"model_refusal_fallback"'


def field(payload: dict, key: str) -> str:
    """jq's `.key // ""`: absent, null and false read as empty; any other value is written as jq -r writes it."""
    found = payload.get(key)
    if found in (None, False):
        return ""
    return found if isinstance(found, str) else json.dumps(found)


def category_of(transcript: str) -> str:
    """apiRefusalCategory of the LAST fallback line; empty when there is no transcript, no such line or it is no JSON."""
    last = b""
    try:
        with open(transcript, "rb") as fh:
            for line in fh:
                if FALLBACK_TOKEN in line:
                    last = line
    except (OSError, ValueError):   # ValueError: a path with a NUL, which read -r dropped (review of #329, F3)
        return ""
    try:
        doc = json.loads(last)
    except ValueError:
        return ""
    return field(doc, "apiRefusalCategory") if isinstance(doc, dict) else ""


def topic_of(category: str) -> str:
    if category.startswith("cyber"):
        return "a cybersecurity issue"
    if category.startswith("bio"):
        return "a biology or biosecurity issue"
    return f"a {category} issue" if category else "the category the safeguard flagged"


def write_marker(directory: str, pid: str, doc: dict) -> None:
    """Sweep the dead sessions' markers, then replace ours; without a directory that is ours, neither."""
    if not plan_hold.hold_directory(directory):
        return
    marker = os.path.join(directory, f"{pid}.json")
    plan_hold.sweep(directory, marker)
    fd, tmp = tempfile.mkstemp(prefix=f".{pid}.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, marker)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def handle(raw: bytes) -> None:
    try:
        payload = json.loads(raw)
    except ValueError:
        return
    if not isinstance(payload, dict) or field(payload, "hook_event_name") != "PostModelSwitch" or field(payload, "source") != "auto":
        return
    origin, target = field(payload, "from_model"), field(payload, "to_model")
    transcript = field(payload, "transcript_path")
    category = category_of(transcript) if transcript else ""
    topic = topic_of(category)
    pid = os.environ.get("CLAUDE_PID") or str(os.getppid())
    if not re.fullmatch(r"[1-9][0-9]*", pid):
        pid = "0"
    session = os.environ.get("CLAUDE_CODE_SESSION_ID") or field(payload, "session_id")
    home = os.environ.get("HOME")
    directory = os.environ.get("AGENT_FABRIC_FALLBACK_DIR") or (os.path.join(home, ".cache", "agent-fabric", "fallback") if home else "")
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if pid != "0" and directory:
        try:
            write_marker(directory, pid, {"session_id": session, "pid": int(pid), "from_model": origin, "to_model": target,
                                          "at": at, "category": category, "topic": topic})
        except OSError:
            pass  # no marker, the note alone
    note = (f"agent-fabric: a safeguard flagged your last request as {topic} and the harness switched this session from "
            f"{origin or 'the launched model'} to {target or 'a fallback model'} at {at}; it stays there until /model. "
            "What flagged you flags every session it reaches, and a broadcast reaches all of them at once. From now on, "
            "filter out of everything you send — GZCoord messages, commit messages, PR bodies, memories — anything that "
            f"could be read as {topic}: name where such a finding is (file, line, PR) and what class of problem it is, "
            "never its content, and let the reader open it in their own repository. "
            "Say in your next report that this session fell back, and to what.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostModelSwitch", "additionalContext": note}}, indent=2, ensure_ascii=False))


def main() -> int:
    raw = sys.stdin.buffer.read()
    # The contract is exit 0 and nothing on stderr, whatever the input: an input the note cannot use is no note, never a
    # traceback (review of #329, F3: a transcript path with a NUL raised ValueError out of open()).
    try:
        if raw.strip():
            handle(raw)
    except Exception:  # noqa: BLE001
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

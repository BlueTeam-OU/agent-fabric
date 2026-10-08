#!/usr/bin/env python3
"""tools/fabric/resume.py — bring this account's last session back, behind
bin/fabric-resume.

    fabric-resume [--print] [-- <launcher args>...]

Run in the account's own shell (after `moveto <account> --resume`, or by a
person), never inside a session. It reads the account's binding (the
session id the session-start hook last recorded), finds that session's
transcript under ~/.claude/projects/, and runs the fabric's launcher with
`--resume <id>` in the directory the session ran in (the transcript's own
`cwd`), so the harness finds it. With no binding session, no transcript or
no directory left, it starts a fresh session in the binding's working copy
and says so: a resume that cannot happen is a fresh start said, never a
failure (architect-cto's plan for Fleet Deck, 2026-10-07; the upgrade
path's relaunch made first-class).

--print says what it would do, one line, and runs nothing. Exit codes: the
launcher's when it runs; 2 inside a session or for a bad argument.

The launcher decides everything else (provider, model, effort, prompt):
this only chooses resume or fresh, and where.
"""
from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FABRIC = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(FABRIC, "runtime"))
import identity  # noqa: E402

# A test points this at a stub; nothing else sets it.
LAUNCHER = os.environ.get("AGENT_FABRIC_RESUME_LAUNCHER") or os.path.join(FABRIC, "runtime", "openrouter", "launch")
SCAN_LINES = 50


def say(msg: str) -> None:
    print(f"fabric-resume: {msg}", file=sys.stderr)


def projects_dir() -> str:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(base, "projects")


def transcript_of(session: str) -> str | None:
    """The session's transcript, wherever its launch directory put it. The
    id is a UUID the harness wrote; anything else is no session."""
    if not session or not all(c.isalnum() or c == "-" for c in session):
        return None
    found = sorted(glob.glob(os.path.join(projects_dir(), "*", f"{session}.jsonl")),
                   key=lambda p: os.stat(p).st_mtime, reverse=True)
    return found[0] if found else None


def cwd_of(transcript: str) -> str | None:
    """The directory the session ran in, from its own records: --resume
    finds a session only from that directory's project."""
    try:
        with open(transcript, encoding="utf-8", errors="replace") as fh:
            for _, line in zip(range(SCAN_LINES), fh):
                try:
                    cwd = json.loads(line).get("cwd")
                except (ValueError, AttributeError):
                    continue
                if isinstance(cwd, str) and cwd:
                    return cwd
    except OSError:
        return None
    return None


def plan() -> tuple[list[str], str, str]:
    """(launcher argv suffix, directory, the line that says it)."""
    binding = identity.read_binding(identity.current_agent())
    session = str(binding.get("session") or "")
    working_copy = str(binding.get("working_copy") or os.path.expanduser("~/projects"))
    transcript = transcript_of(session)
    cwd = cwd_of(transcript) if transcript else None
    if transcript and cwd and os.path.isdir(cwd):
        return ["--resume", session], cwd, f"resuming session {session} in {cwd}"
    why = ("no session recorded" if not session else
           f"no transcript of session {session}" if not transcript else
           f"session {session}'s directory is gone")
    start = working_copy if os.path.isdir(working_copy) else os.path.expanduser("~")
    return [], start, f"{why}; starting fresh in {start}"


def main(argv: list[str]) -> int:
    if os.environ.get("CLAUDECODE"):
        say("run it in the account's shell, not inside a session (it starts one)")
        return 2
    show = False
    extra: list[str] = []
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--print":
            show = True
        elif a == "--":
            extra = args
            break
        elif a in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        else:
            say(f"unexpected argument: {a}")
            return 2
    suffix, cwd, line = plan()
    if show:
        print(line)
        return 0
    say(line)
    os.chdir(cwd)
    os.execv(LAUNCHER, [LAUNCHER, *extra, *suffix])
    return 0  # not reached


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

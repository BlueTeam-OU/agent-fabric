#!/usr/bin/env python3
"""Contract test of runtime/claude-code/hooks/session-start.sh, the path the
harness runs for SessionStart (Wave 9 batch 6; the oracle of the port,
ADR-040 rule 5). The entry point is ENTRY, run as the harness runs it: a
program with the hook payload on stdin; $SESSION_START_HOOK aims the same
test at its replacement. What the module behind it says (the context line,
the project layer, the job list) is tests/test_session_start.py's; this file
holds what the script itself owes the harness: the export into the session's
shell, the root it resolves, and that it never fails.

There is no bash test for this script; its cases are the ones its header
and its comments name:
  1 stdout is one SessionStart object whose additionalContext is non-empty,
  exit 0, from an environment with nothing in it; 2 $CLAUDE_ENV_FILE gets
  `export AGENT_FABRIC_ROOT=<root>` (the root is the checkout the script
  lives in, found through a symlink to it too); 3 the line is written once:
  resume and compaction run the hook again; 4 an env file that already
  carries the export (any value) is left as it is; 5 an AGENT_FABRIC_ROOT
  already set is the root exported, quoted so a path with spaces and quotes
  survives being sourced; 6 no CLAUDE_ENV_FILE: exit 0; 7 an
  env file that cannot be written (it is a directory): exit 0 and the
  context still printed; 8 a broken control plane (a root with no module,
  no python3 on PATH) and 9 a payload that is no JSON: exit 0; 10 the line sourced in a clean
  shell sets AGENT_FABRIC_ROOT, the variable every documented
  `$AGENT_FABRIC_ROOT/...` command expands.

Mutations, each failing here: the grep guard removed (3, 4); `%q` replaced
by `%s` (5); `readlink -f` removed (2 through the link); the final `exit 0`
removed (8, with no interpreter); AGENT_FABRIC_ROOT forced to FABRIC_ROOT (5).

Exit codes: 0 all assertions passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import hook_harness as h
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()

ENTRY = h.entry("SESSION_START_HOOK", "session-start.sh")
T = h.sandbox("test_session_start_hook_cli.")
HOME = os.path.join(T, "home")
STATE = os.path.join(T, "state")
t = h.Tests("session start")
PAYLOAD = json.dumps({"hook_event_name": "SessionStart", "session_id": "s", "source": "startup", "cwd": "/"})


def environment(**extra: str) -> dict[str, str]:
    return h.env(HOME, **{"AGENT_FABRIC_STATE_DIR": STATE, **extra})


def start(payload: str = PAYLOAD, **extra: str) -> h.Result:
    return h.run(ENTRY, payload, environment(**extra))


def exported(env_file: str) -> str | None:
    """AGENT_FABRIC_ROOT as a clean shell sources it out of the env file."""
    p = subprocess.run(["bash", "-c", f'source "{env_file}" && printf %s "$AGENT_FABRIC_ROOT"'], env=h.env(HOME), capture_output=True, text=True, timeout=60)
    return p.stdout if p.returncode == 0 else None


def lines_of(env_file: str) -> list[str]:
    with open(env_file, encoding="utf-8") as fh:
        return [ln for ln in fh.read().splitlines() if ln.startswith("export AGENT_FABRIC_ROOT=")]


def main() -> int:
    os.makedirs(HOME)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(ENTRY))))

    t.group("what the harness reads")
    r = start()
    try:
        doc = json.loads(r.out)["hookSpecificOutput"]
    except (ValueError, KeyError, TypeError):
        doc = {}
    t.check("exit 0 and one SessionStart object with a context", r.rc == 0 and doc.get("hookEventName") == "SessionStart" and bool(doc.get("additionalContext")), f"{r.rc} {r.out!r} {r.err!r}")

    t.group("the export into the session's shell")
    env_file = os.path.join(T, "claude-env")
    r = start(CLAUDE_ENV_FILE=env_file)
    t.check("the env file gets the export of the checkout's root", r.rc == 0 and exported(env_file) == root, f"{exported(env_file)!r} != {root!r}; {r.err}")
    start(CLAUDE_ENV_FILE=env_file)
    start(CLAUDE_ENV_FILE=env_file)
    t.check("written once: resume and compaction run the hook again", len(lines_of(env_file)) == 1, str(lines_of(env_file)))
    link_dir = os.path.join(T, "linked")
    os.makedirs(link_dir)
    link = os.path.join(link_dir, "session-start.sh")
    os.symlink(ENTRY, link)
    other = os.path.join(T, "claude-env-link")
    r = h.run(link, PAYLOAD, environment(CLAUDE_ENV_FILE=other))
    t.check("run through a symlink, the root is still the checkout the script lives in", exported(other) == root, f"{exported(other)!r}; {r.err}")
    prior = os.path.join(T, "claude-env-prior")
    with open(prior, "w", encoding="utf-8") as fh:
        fh.write("export AGENT_FABRIC_ROOT=/somewhere/else\nexport KEEP=1\n")
    start(CLAUDE_ENV_FILE=prior)
    with open(prior, encoding="utf-8") as fh:
        # The module appends its own lines (the secrets it unsets); the root's export is the one the script owns.
        t.check("an env file that already exports it keeps that one export and its lines",
                fh.read().startswith("export AGENT_FABRIC_ROOT=/somewhere/else\nexport KEEP=1\n") and lines_of(prior) == ["export AGENT_FABRIC_ROOT=/somewhere/else"])
    appended = os.path.join(T, "claude-env-append")
    with open(appended, "w", encoding="utf-8") as fh:
        fh.write("export KEEP=1\n")
    start(CLAUDE_ENV_FILE=appended)
    with open(appended, encoding="utf-8") as fh:
        t.check("another export in the file is kept, ours appended after it", fh.read().startswith("export KEEP=1\nexport AGENT_FABRIC_ROOT="))

    t.group("a root that is already set is the root exported")
    awkward = "/tmp/a b/it's $HOME/\"q\""
    quoted = os.path.join(T, "claude-env-quoted")
    r = start(CLAUDE_ENV_FILE=quoted, AGENT_FABRIC_ROOT=awkward)
    t.check("…quoted, so spaces, quotes and a dollar survive being sourced", r.rc == 0 and exported(quoted) == awkward, f"{exported(quoted)!r}")
    t.check("…with exit 0 although that root holds no module", r.rc == 0, f"{r.rc} {r.err}")

    t.group("never fails")
    r = start()
    t.check("no CLAUDE_ENV_FILE: exit 0", r.rc == 0, f"{r.rc}")
    unwritable = os.path.join(T, "env-is-a-directory")
    os.makedirs(unwritable)
    r = start(CLAUDE_ENV_FILE=unwritable)
    t.check("an env file that cannot be written: exit 0, and the context is still printed", r.rc == 0 and "SessionStart" in r.out, f"{r.rc} {r.out!r}")
    r = start(AGENT_FABRIC_ROOT=os.path.join(T, "nowhere"))
    t.check("a broken control plane (a root with no module): exit 0", r.rc == 0, f"{r.rc}")
    no_python = h.tool_dir(os.path.join(T, "no-python"), ["bash", "env", "grep", "dirname", "readlink", "cat", "id"])
    gone_env = os.path.join(T, "claude-env-nopython")
    r = h.run(ENTRY, PAYLOAD, {**environment(CLAUDE_ENV_FILE=gone_env), "PATH": no_python})
    t.check("no interpreter to run the module: still exit 0, and the export is already written",
            r.rc == 0 and exported(gone_env) == root, f"{r.rc} {exported(gone_env)!r} {r.err!r}")
    r = start("not json")
    t.check("a payload that is no JSON: exit 0", r.rc == 0, f"{r.rc} {r.err!r}")
    r = start("")
    t.check("an empty payload: exit 0", r.rc == 0, f"{r.rc} {r.err!r}")
    return t.finish()


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(T, ignore_errors=True)

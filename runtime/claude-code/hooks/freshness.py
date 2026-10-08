#!/usr/bin/env python3
"""runtime/claude-code/hooks/freshness.py — keep a session's view of its
working copy's remote fresh, and say when its checkout is behind it.

Sessions reasoned about a repository from a checkout days behind its
origin: a rule its project had replaced, a pull request already merged, a
file already rewritten (the owner, 2026-10-07: "an agent doesn't even
fetch the last version of a repo before starting reasoning about it").
The prompt says to read the remote ref; a rule in prose was not enough.

Registered at user scope (runtime/claude-code/user-settings.py) on
UserPromptSubmit, so it runs for every session of the account in whatever
working copy it is in. On each prompt, for the git working copy of the
payload's `cwd`:

  - when its last fetch (FETCH_HEAD's time) is older than FETCH_EVERY_S,
    a `git fetch --quiet origin` is started DETACHED: the prompt never
    waits on the network, and the next prompt sees the fetched refs;
  - when HEAD lacks commits of origin's default branch, one line goes to
    the model as context — how many, as of when — and only when that
    count changed since this session last heard it, so a session is told
    once, not on every prompt.

Nothing is printed when the copy is current, when `cwd` is no git working
copy, or when anything fails: a hook must never stand in a session's
way. It writes nothing but its own per-session note in the account's
state directory, and starts nothing but that fetch.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

FETCH_EVERY_S = 600
# At most six local git calls run in a prompt (the fallback refs
# included), inside the hook's 15 s budget (user-settings.py): a hook past
# its timeout says nothing at all. Each is a local read, milliseconds.
GIT_TIMEOUT_S = 2
FETCH_TIMEOUT_S = 120
SESSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def git(top: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", top, *args], capture_output=True, text=True, timeout=GIT_TIMEOUT_S,
                          stdin=subprocess.DEVNULL, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def state_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, "..", ".."))
    import identity  # runtime/identity.py
    return identity.agent_state_dir()


def fetch_detached(top: str) -> None:
    """A fetch nobody waits for: its own session, no terminal, bounded."""
    subprocess.Popen(["timeout", str(FETCH_TIMEOUT_S), "git", "-C", top, "fetch", "--quiet", "origin"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def note(payload: dict, now: float | None = None, state: str | None = None) -> str | None:
    """The line for the model, or None; starts a fetch when one is due."""
    now = time.time() if now is None else now
    cwd = payload.get("cwd")
    session = str(payload.get("session_id") or "")
    if not isinstance(cwd, str) or not os.path.isdir(cwd) or not SESSION_RE.match(session):
        return None
    # --git-path, not the common dir: a linked worktree's fetch writes its
    # own FETCH_HEAD, so the common one would throttle on another checkout.
    r = git(cwd, "rev-parse", "--show-toplevel", "--git-path", "FETCH_HEAD")
    if r.returncode != 0:
        return None
    top, fetch_head = (r.stdout.splitlines() + ["", ""])[:2]
    fetch_head = fetch_head if os.path.isabs(fetch_head) else os.path.join(cwd, fetch_head)
    if git(top, "remote", "get-url", "origin").returncode != 0:
        return None
    try:
        fetched = os.stat(fetch_head).st_mtime
    except OSError:
        fetched = None
    if fetched is None or now - fetched > FETCH_EVERY_S:
        fetch_detached(top)
    # origin/HEAD is absent after `git remote add` (a fetch does not create
    # it); then the first of main and master that exists, else nothing is
    # said: a missing ref must never read as "current" (#111 review).
    ref = git(top, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD").stdout.strip()
    # origin/HEAD may also name a branch the remote has since deleted.
    if ref and git(top, "rev-parse", "--verify", "--quiet", f"refs/remotes/{ref}").returncode != 0:
        ref = ""
    if not ref:
        ref = next((c for c in ("origin/main", "origin/master")
                    if git(top, "rev-parse", "--verify", "--quiet", f"refs/remotes/{c}").returncode == 0), "")
    if not ref:
        return None
    n = git(top, "rev-list", "--count", f"HEAD..{ref}")
    behind = int(n.stdout) if n.returncode == 0 and n.stdout.strip().isdigit() else 0
    path = os.path.join(state or state_dir(), f"freshness-{session}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            said = json.load(fh)
    except (OSError, ValueError):
        said = {}
    if not isinstance(said, dict):
        said = {}
    if said.get(top, 0) == behind:
        return None
    # A note is kept only while there is a gap to remember: a current copy
    # leaves nothing behind for a session that never fell behind.
    if behind:
        said[top] = behind
    else:
        said.pop(top, None)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    if said:
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(said, fh)
        os.replace(tmp, path)
    else:
        try:
            os.remove(path)
        except OSError:
            pass
    if behind == 0:
        return None
    age = "never fetched" if fetched is None else f"fetched {int((now - fetched) // 60)} min ago"
    branch = git(top, "symbolic-ref", "-q", "--short", "HEAD").stdout.strip() or "(detached)"
    return (f"agent-fabric: {top} ({branch}) lacks {behind} commit(s) of {ref} ({age}). Before reasoning about "
            f"this repository's code, rules or pull requests, read {ref}, not the checkout: `git fetch`, then "
            f"`git log HEAD..{ref}` or `git show {ref}:<path>`.")


def main() -> int:
    try:
        line = note(json.load(sys.stdin))
        if line:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                     "additionalContext": line}}))
    except Exception:  # noqa: BLE001 - a hook never stands in a session's way
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

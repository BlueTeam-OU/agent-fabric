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

Nothing is printed by the freshness part when the copy is current, when
`cwd` is no git working copy, or when it fails: a hook must never stand in
a session's way. The same prompt also carries the git rules
(tools/fabric/git_rules.py, ADR-019 §5 rule 9) when `cwd`'s working copy is
another than the one the session was last given them for (in a directory
that is no working copy too, where they are the operator layer on the
fleet's policy), and one line saying so when they cannot be given. It
writes nothing but its two per-session notes in the account's state
directory (freshness-<session>.json, git-rules-<session>.json), reads the
account's copy of the policy, and starts nothing but that fetch.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import time

FETCH_EVERY_S = 600
# At most eight local git calls run in the freshness part of a prompt (the
# dangling-ref check and both fallback refs included) and five in the rules
# part (its own toplevel, then the renderer's toplevel, resolve's two and the
# origin read), each bounded by GIT_TIMEOUT_S, inside the hook's 15 s budget
# (user-settings.py): a hook past its timeout says nothing at all. Each is a
# local read, milliseconds; but both parts at their worst take 19.5 s, so the
# rules part renders only while RULES_NEEDS_S of the budget is left; its own
# toplevel, its module load and the given-note are read before that check,
# whatever is left (RULES_NEEDS_S still counts that first call).
GIT_TIMEOUT_S = 1.5
HOOK_BUDGET_S = 14.0       # 15 s less Python's start
RULES_NEEDS_S = 5 * GIT_TIMEOUT_S
FETCH_TIMEOUT_S = 120
SESSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def git(top: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", top, *args], capture_output=True, text=True, timeout=GIT_TIMEOUT_S,
                          stdin=subprocess.DEVNULL, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def identity():
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, "..", ".."))
    import identity  # runtime/identity.py, the state layer's one writer (ADR-003 rule 1)
    return identity


def state_dir() -> str:
    return identity().agent_state_dir()


def process():
    """tools/fabric/process.py, loaded by path: the one owner of starting a command in a session of its own."""
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("fabric_process", os.path.join(here, "..", "..", "..", "tools", "fabric", "process.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch_detached(top: str) -> None:
    """A fetch nobody waits for: its own session, no terminal, bounded."""
    process().spawn_service(["timeout", str(FETCH_TIMEOUT_S), "git", "-C", top, "fetch", "--quiet", "origin"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def note(payload: dict, now: float | None = None, state: str | None = None) -> str | None:
    """The line for the model, or None; starts a fetch when one is due."""
    now = time.time() if now is None else now
    cwd = payload.get("cwd")
    session = str(payload.get("session_id") or "")
    if not isinstance(cwd, str) or not os.path.isdir(cwd) or not SESSION_RE.fullmatch(session):
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
        identity().atomic_write(path, json.dumps(said), 0o600)
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


def git_rules_note(payload: dict, state: str | None = None, budget_left=None) -> str | None:
    """The git rules (ADR-019 §5 rule 9) for the prompt's working copy when it is another than the one this session was
    last given them for (session-start.py gives them and notes it), else None. Independent of the remote: a copy with
    no origin has rules too. Outside a git working copy it is the operator layer on the fleet's policy, once."""
    cwd, session = payload.get("cwd"), str(payload.get("session_id") or "")
    if not isinstance(cwd, str) or not os.path.isdir(cwd) or not SESSION_RE.fullmatch(session):
        return None
    top = git(cwd, "rev-parse", "--show-toplevel").stdout.strip() or None
    rules = git_rules()
    if not rules.changed(session, top, state):
        return None
    if budget_left is not None and budget_left() < RULES_NEEDS_S:
        # Not recorded as given, so a later prompt asks again.
        return "agent-fabric: the git rules were not given on this prompt (the hook's time was spent); they are given on a later prompt."
    text = rules.for_hook(top, timeout=GIT_TIMEOUT_S)
    # Only text that was rendered is noted as given: a failure line says no rules, so the next prompt tries again.
    if not text.startswith(rules.FAILURE_PREFIX):
        rules.record_given(session, top, state)
    return text


def git_rules():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("fabric_git_rules", os.path.join(here, "..", "..", "..", "tools", "fabric", "git_rules.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 - a hook never stands in a session's way
        return 0
    lines = []
    started = time.monotonic()
    # Each on its own: a failure of the freshness note must not cost the session the rules, nor the reverse.
    try:
        line = note(payload)
        if line:
            lines.append(line)
    except Exception:  # noqa: BLE001
        pass
    try:
        # The budget is applied only once rules are due: a session already given them hears nothing about them.
        line = git_rules_note(payload, budget_left=lambda: HOOK_BUDGET_S - (time.monotonic() - started))
        if line:
            lines.append(line)
    except Exception as e:  # noqa: BLE001 - said, not raised: silence would read as "no rules apply"
        lines.append(f"agent-fabric: the git rules could not be given ({type(e).__name__}: {e}); run fabric-git-rules")
    try:
        if lines:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                     "additionalContext": "\n\n".join(lines)}}))
    except Exception:  # noqa: BLE001 - a hook never stands in a session's way
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

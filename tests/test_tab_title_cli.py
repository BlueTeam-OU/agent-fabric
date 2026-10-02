#!/usr/bin/env python3
"""The oracle for runtime/claude-code/hooks/tab-title.sh (ported from
test_tab-title.sh): the hook's OUTPUT CONTRACT, and that it NEVER FAILS LOUDLY.

Claude Code reads one field, "terminalSequence", and silently drops anything
outside a narrow escape allowlist -- so a wrong shape does not error, it just
stops setting the title, indistinguishable from the feature never having been
wired. The hook runs after every Bash tool call; a non-zero exit or stray
stdout on a malformed payload would turn a cosmetic feature into a broken
session. Each case runs the REAL script against a throwaway git repo.

The hook under test is $TAB_TITLE_HOOK, default the one the bash test runs.

Exit codes: 0 all assertions passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.environ.get("TAB_TITLE_HOOK") or os.path.join(HERE, "runtime", "claude-code", "hooks", "tab-title.sh")
if not os.path.isfile(HOOK):
    sys.exit(f"test: not found: {HOOK}")

T = tempfile.mkdtemp(prefix="test_tab_title_cli.")
HOME = f"{T}/home"
fails = 0


def check(label: str, good: bool, detail: str = "") -> None:
    global fails
    if good:
        print(f"  ok   {label}")
        return
    fails += 1
    print(f"  FAIL {label}: {detail}" if detail else f"  FAIL {label}")


def clean_env() -> dict[str, str]:
    # GIT_* (GIT_DIR, GIT_INDEX_FILE from a run inside a hook) and XDG_* (a real
    # git config or binding) would point the fixture at the caller's (review of #83).
    e = {k: v for k, v in os.environ.items()
         if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "CLAUDE_", "GZCOORD_", "GIT_", "XDG_")) and k != "CLAUDECODE"}
    e.update(HOME=HOME, XDG_STATE_HOME=f"{T}/state", XDG_CONFIG_HOME=f"{T}/config")
    return e


def hook(payload: str, cwd: str | None = None) -> tuple[int, str]:
    p = subprocess.run(["bash", HOOK], input=payload.encode(), env=clean_env(), cwd=cwd,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
    return p.returncode, p.stdout.decode("utf-8", "surrogateescape")


def run_hook(d: str) -> tuple[int, str]:
    return hook(json.dumps({"cwd": d}))


def title_of(out: str) -> str:
    """The payload between the OSC 0 introducer and the BEL."""
    raw = out.strip()
    if not raw:
        return "<no output>"
    d = json.loads(raw)
    if list(d) != ["terminalSequence"]:
        return f"<unexpected keys: {list(d)}>"
    s = d["terminalSequence"]
    if not (s.startswith("\x1b]0;") and s.endswith("\x07")):
        return f"<unexpected framing: {s!r}>"
    return s[4:-1]


def assert_eq(label: str, want: str, got: str) -> None:
    check(label, want == got, f"want: {want}\n       got:  {got}")


def git(*args: str, repo: str) -> str:
    # HERMETIC, and loud when it cannot be built. The fixture used to inherit
    # the contributor's global git config: this repo installs a git GPG shim,
    # so an ordinary `commit.gpgsign = true` with an unavailable key made the
    # empty commit fail, HEAD stay unborn, and the detached-HEAD case then
    # report a FAILURE AGAINST CORRECT CODE. A fixture that half-builds and
    # keeps going blames the thing under test for its own breakage.
    p = subprocess.run(["git", "-C", repo, *args], env=clean_env(), capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"test: fixture setup failed: git {' '.join(args)}\n{p.stderr}")
    return p.stdout.strip()


def sh_out(*cmd: str) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, env=clean_env()).stdout.strip()


def main() -> int:
    os.makedirs(HOME)
    sandbox = f"{T}/sandbox"
    repo = f"{sandbox}/my-clone"
    os.makedirs(repo)
    git("-c", "init.defaultBranch=main", "init", "-q", repo=repo)
    git("config", "user.email", "t@example.invalid", repo=repo)
    git("config", "user.name", "test", repo=repo)
    git("config", "commit.gpgsign", "false", repo=repo)
    git("config", "gpg.format", "openpgp", repo=repo)
    git("commit", "-q", "--allow-empty", "-m", "first", repo=repo)
    git("branch", "-M", "main", repo=repo)

    # The agent (the login) leads the title; the working copy and branch follow.
    agent = sh_out("id", "-un")
    assert_eq("the title is <agent> <working-copy>/<branch>", f"{agent} my-clone/main", title_of(run_hook(repo)[1]))

    # Branches here are <host>/<clone>/<type>/<desc>; used whole, the clone
    # appears twice and the task falls off the end of a narrow tab.
    host = sh_out("hostname", "-s") or sh_out("hostname")
    git("checkout", "-q", "-b", f"{host}/my-clone/feat/some-task", repo=repo)
    assert_eq("this working copy's own (legacy) branch prefix is stripped",
              f"{agent} my-clone/feat/some-task", title_of(run_hook(repo)[1]))

    # The current convention names the AGENT in the second segment.
    git("checkout", "-q", "-b", f"{host}/{agent}/feat/mine", repo=repo)
    assert_eq("this agent's branch prefix is stripped", f"{agent} my-clone/feat/mine", title_of(run_hook(repo)[1]))

    # A prefix belonging to a DIFFERENT clone is not this clone's, so it stays:
    # stripping it would claim work that is not ours.
    git("checkout", "-q", "-b", f"{host}/other-clone/feat/theirs", repo=repo)
    assert_eq("another session's prefix is left alone",
              f"{agent} my-clone/{host}/other-clone/feat/theirs", title_of(run_hook(repo)[1]))

    # Every subagent worktree runs in a detached HEAD.
    git("checkout", "-q", "--detach", repo=repo)
    sha = git("rev-parse", "--short", "HEAD", repo=repo)
    assert_eq("detached HEAD shows the short SHA, not an empty half-title",
              f"{agent} my-clone/{sha}", title_of(run_hook(repo)[1]))

    # Every subagent dispatch runs in a linked worktree on its own generated
    # branch. Resolving "here" titled the tab agent-<id>/worktree-agent-<id>,
    # which names neither the clone nor the task, and it persisted after the
    # agent finished until the session ran a Bash call of its own.
    git("checkout", "-q", "main", repo=repo)
    linked = f"{sandbox}/linked/agent-probe"
    git("worktree", "add", "-q", "-b", "worktree-agent-probe", linked, "main", repo=repo)
    assert_eq("a linked worktree reports the main clone and ITS branch",
              f"{agent} my-clone/main", title_of(run_hook(linked)[1]))
    subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", linked], env=clean_env(),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Outside a repo there is no title to set, and saying so with an empty body
    # is how a hook declines: any stdout here would be parsed as a directive.
    rc, out = hook('{"cwd":"/"}')
    check("outside a git repo it emits nothing and exits 0", out == "" and rc == 0, f"rc={rc} out=[{out}]")

    # A valid payload must ALSO exit 0. Without this the malformed cases below
    # only pin the short-circuit at the top of the script, not the path that
    # actually emits -- they reach the emit only because the suite happens to
    # run from inside a repo, so `dir` falls back to $PWD.
    rc, out = run_hook(repo)
    check("a valid payload emits a sequence and still exits 0", rc == 0 and out != "", f"rc={rc} out=[{out}]")

    # The bash ran these from the checkout (a repo), so $PWD is one here too.
    for payload in ('{}', 'not json at all', ''):
        rc, out = hook(payload, cwd=HERE)
        check(f"a malformed payload ({payload or 'empty'}) still exits 0", rc == 0, f"rc={rc}")

    # The escapes are written as jq's backslash-u001b / backslash-u0007 text. A
    # literal ESC in a tracked file survives git but not every editor, diff
    # view or copy-paste, and it is invisible in review.
    with open(HOOK, encoding="utf-8") as f:
        s = f.read()
    check("the script source is free of raw control bytes", not [c for c in s if ord(c) < 32 and c not in "\n\t"])

    print()
    if fails:
        print(f"{fails} FAILED")
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(T, ignore_errors=True)

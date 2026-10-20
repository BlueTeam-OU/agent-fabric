#!/usr/bin/env python3
"""tools/fabric/statusline.py — the Claude Code status line, behind
runtime/claude-code/hooks/statusline.sh (Wave 9 batch 7, ADR-040 §7):

    [harness version · model · effort] 👤 agent@host <pull request> 📁 working copy <git ref>

Contract, frozen from the shell script and pinned by tests/test_statusline_cli.py:
  stdin   the session JSON the harness sends on every refresh; a payload that is not JSON reads as
          one with nothing in it, except that the model is then empty, as jq left it
  stdout  the one line, no trailing newline; nothing on stderr; exit 0
  env     HOME / XDG_CACHE_HOME (the pull-request cache), GH_REPO, AGENT_FABRIC_STATUSLINE_PR_TTL (seconds, 120
          when unset or empty; one that is no integer never counts a cache entry fresh), PATH (git, gh)
  writes  <cache>/agent-fabric/statusline/pr-<key>, replaced whole; and, through runtime/claude-code/hooks/
          context-sample.py, the context share kept beside the session state (never waits more than 2 s,
          never prints, never fails the line)

THE AGENT is the Linux login, from bin/fabric-whoami; the folder is the working copy the session is in —
context, never identity. Runs on every refresh and calls no API: start-up is kept cheap, so nothing is
imported until a branch needs it.

THE HARNESS BRACKET (owner, 2026-09-24): the Claude Code version (the bare number — the owner asked for no
product name before it), the model and the session's live effort level, in that order — the three things that
decide how this session thinks, readable at a glance and comparable across sessions (a session that reads
"high" beside another's "medium" is a routing question; routing/effort.json says what each class asks for).
All are read from the session JSON, never from the environment: `version` is the harness's own; `effort` is
optional in that JSON — present only when the model takes an effort level — so a model that expresses none
shows NO level rather than an invented one, and an older harness that sends no version shows the model alone.

THE REF exists only inside a repository, and its icon says which state it is: 🌿 a branch (an unborn one
still has its name); 🔗 a detached HEAD, with its short SHA — a link straight to a commit, not a branch
(owner, 2026-09-15). Outside a repository — the parent projects/ workspace, by design — there is no segment at
all. It used to print "🌿 detached" for both a detached HEAD and no repository, and a session launched from
projects/ read as sitting on a branch nobody had made.

THE PULL REQUEST the branch is in, before the folder (owner, 2026-09-18): 🔀 #386 for an open one, ✅ #386
once merged (the branch is done — go back to main), 🚫 #386 for a closed one, 🔀 N/A for a branch with no pull
request, and nothing on a detached HEAD or outside a repository (no branch, no question). gh is asked at most
once per TTL per (working copy, branch) — the status line redraws on every turn and a network call each time
would be felt and rate-limited — through a small cache under XDG_CACHE_HOME; a gh that is missing, fails or
does not answer within GH_TIMEOUT_S reads as "?" (unknown), never as N/A, because "no pull request" is a fact
about GitHub and this line does not invent facts it could not read. An unknown is not cached: the next redraw
asks again.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
# The forwarders run this file under `python -I`, which leaves its own directory off sys.path; first, so that
# `git` is this directory's and not an installed package of that name.
sys.path.insert(0, HERE)
import git  # noqa: E402
import hook_common  # noqa: E402

CONTEXT_SAMPLE = os.path.join(hook_common.ROOT, "runtime", "claude-code", "hooks", "context-sample.py")
CONTEXT_TIMEOUT_S = 2
GIT_TIMEOUT_S = 10
GH_TIMEOUT_S = 10
DEFAULT_TTL_S = 120
# Where an unknown repository is named from: the form tools/fabric/gh.py's this_repo reads.
ORIGIN = r"([^@/:]+@github\.com:|(https|ssh|git)://([^@/]+@)?github\.com/)([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)/?"


UNPARSABLE = object()


def field(payload: object, *path: str, default: str = "") -> str:
    """jq's `-r '.a.b // default'` over the payload: `default` for an absent, null or false value, "" where jq
    would fail (a key looked up in a list or a string), the text of a number or true as jq prints it. An empty
    string is a value."""
    for key in path:
        if payload is None:
            return default
        if not isinstance(payload, dict):
            return ""
        payload = payload.get(key)
    if payload is None or payload is False:
        return default
    return payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def sample_context(raw: bytes) -> None:
    try:
        subprocess.run([sys.executable, CONTEXT_SAMPLE], input=raw, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=CONTEXT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        pass


def git_out(directory: str, *args: str) -> str:
    try:
        return git.out(directory, *args, timeout=GIT_TIMEOUT_S)
    except git.GitError:
        return ""


def repository(directory: str) -> str:
    """The repository gh is asked about, as tools/fabric/gh.py's this_repo names it: GH_REPO, else origin on
    github.com; never gh's default, which in a fork clone is the upstream project (agent-fabric #109)."""
    named = os.environ.get("GH_REPO", "")
    if named:
        return named
    import re
    found = re.fullmatch(ORIGIN, git_out(directory, "remote", "get-url", "origin"))
    return re.sub(r"(\.git)?/?$", "", found.group(4), count=1) if found else ""


def ask_gh(directory: str, repo: str, branch: str) -> str:
    """"<STATE> <number>" of the newest pull request for the head branch, open first; "none"; or "unknown"."""
    import shutil
    if not repo or not shutil.which("gh"):
        return "unknown"
    import gh   # the one door to GitHub: its ledger counts this call too
    try:
        out = gh.run(["pr", "list", "--repo", repo, "--head", branch, "--state", "all", "--limit", "5",
                      "--json", "number,state"], cwd=directory, timeout=GH_TIMEOUT_S, lookups=False)
        rows = json.loads(out)
    except (gh.GhError, OSError, ValueError):
        return "unknown"
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return "unknown"
    if not rows:
        return "none"
    first = sorted(rows, key=lambda row: row.get("state") != "OPEN")[0]
    number = first.get("number")
    if not isinstance(first.get("state"), str) or not isinstance(number, int):
        return "unknown"
    return f"{first['state']} {number}"


def pull_request(directory: str, toplevel: str, branch: str) -> str:
    import hashlib
    ttl = os.environ.get("AGENT_FABRIC_STATUSLINE_PR_TTL") or str(DEFAULT_TTL_S)
    cache_dir = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(os.environ.get("HOME", ""), ".cache"),
                             "agent-fabric", "statusline")
    cache = os.path.join(cache_dir, "pr-" + hashlib.sha256(f"{toplevel}\n{branch}".encode("utf-8", "surrogateescape")).hexdigest()[:16])
    fresh = ""
    try:
        if time.time() - os.stat(cache).st_mtime < int(ttl):
            with open(cache, encoding="utf-8", errors="replace") as fh:
                fresh = fh.read().rstrip("\n")
    except (OSError, ValueError):
        pass
    if not fresh:
        fresh = ask_gh(directory, repository(directory), branch)
        if fresh != "unknown":
            store(cache_dir, cache, fresh)
    state, _, number = fresh.partition(" ")
    if number:
        icon = {"OPEN": "🔀", "MERGED": "✅", "CLOSED": "🚫"}.get(state)
        if icon:
            return f"{icon} #{number}"
    return "🔀 N/A" if fresh == "none" else "🔀 #?"


def store(cache_dir: str, cache: str, text: str) -> None:
    """Replaced whole, so a redraw racing this one never reads half an answer; a cache that cannot be written
    costs the next redraw a question and nothing else."""
    tmp = f"{cache}.{os.getpid()}"
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, cache)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def line(raw: bytes) -> str:
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = UNPARSABLE
    directory = field(payload, "workspace", "current_dir") or hook_common.current_directory()
    # A payload jq cannot read leaves the model empty, as its failure did; one that merely lacks it is "Claude".
    model = field(payload, "model", "display_name", default="" if payload is UNPARSABLE else "Claude")
    harness = model
    if version := field(payload, "version"):
        harness = f"{version} · {harness}"
    if effort := field(payload, "effort", "level"):
        harness = f"{harness} · {effort}"
    toplevel = git_out(directory, "rev-parse", "--show-toplevel")
    ref = branch = ""
    if toplevel:
        branch = git_out(directory, "branch", "--show-current")
        if branch:
            ref = f" 🌿 {branch}"
        elif sha := git_out(directory, "rev-parse", "--short", "HEAD"):
            ref = f" 🔗 {sha}"
    pr = f" {pull_request(directory, toplevel, branch)}" if branch else ""
    folder = os.path.basename(toplevel or directory.rstrip("/")) or "/"
    return f"[{harness}] 👤 {hook_common.agent_name()}@{hook_common.short_host()}{pr} 📁 {folder}{ref}"


def main() -> int:
    raw = sys.stdin.buffer.read()
    sample_context(raw)
    text = line(raw)
    try:
        out = text.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        # A lone surrogate the payload spelled as an escape (a high surrogate) is no path byte; jq refused such JSON, the line is drawn.
        out = text.encode("utf-8", "replace")
    sys.stdout.buffer.write(out)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())

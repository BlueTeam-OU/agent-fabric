#!/usr/bin/env python3
"""Contract test of runtime/claude-code/hooks/statusline.sh, the Claude Code
status line (Wave 9 batch 7; the oracle of the port, ADR-040 rule 5). The
entry point is ENTRY, run as the harness runs it: a program with the session
JSON on stdin and the line on stdout; $STATUSLINE_HOOK aims the same test at
its replacement. gh is a mock on PATH (it records its arguments), the cache
lives under the case's XDG_CACHE_HOME, every case runs the real script
against a throwaway git repository.

Every case of runtime/claude-code/hooks/test_statusline.sh:
  1 inside a repository with no pull request: `🔀 N/A` before the folder,
  then the branch; 2 a fork clone asks about origin's repository, never
  upstream's; 3 an open pull request: `🔀 #386`; 4 a merged one: `✅ #386`;
  5 an open PR wins over an older merged one on the same branch; 6 gh
  failing: `#?` (unknown), never N/A; 7 within the TTL the cached answer is
  drawn and gh is not asked; 8 no repository named (origin off github.com,
  no GH_REPO): `#?`, and gh is not asked; 9 a detached HEAD: `🔗` and the
  short SHA, no branch icon, no pull-request segment; 10 …and no branch
  icon; 11 outside a repository: no ref segment and no pull-request
  segment; 12 a repository with no commit yet: its branch name, `🔀 N/A`;
  13 …and the word "detached" appears nowhere; 14 the bracket reads the bare
  version · model · effort in that order; 15 no effort block: version ·
  model, no level invented; 16 neither sent: the model alone.
Added where a refactor could break the contract: the whole line, byte for
byte, with no trailing newline and nothing on stderr; exit 0; a closed PR
`🚫`; the repository named by GH_REPO over origin, and the https, ssh://
and `.git`-less forms of origin; the exact gh arguments (repo, head,
state all); the cache is per branch and an unknown is not cached; no PR
asked about on a detached HEAD or outside a repository; a payload with
no workspace falls back to $PWD and an empty one to the model "Claude";
the agent is the login and the host the short hostname; no `gh` on PATH:
`#?`.

Mutations, each failing here: GH_REPO ignored (the GH_REPO case); "none"
shown as `#?` (case 1); gh failure cached (the unknown-is-not-cached case);
the open-first sort removed (case 5); `🔗` replaced by `🌿` (case 9); the
version dropped from the bracket (case 14); a trailing newline added (the
whole-line case); the closed icon changed (closed case); the $PWD fallback
changed (thin payload).

Exit codes: 0 all assertions passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys

import hook_harness as h

ENTRY = h.entry("STATUSLINE_HOOK", "statusline.sh")
T = h.sandbox("test_statusline_cli.")
HOME = os.path.join(T, "home")
BIN = os.path.join(T, "bin")
CALLS = os.path.join(T, "ghcalls")
PRS = os.path.join(T, "pr")
FAIL = os.path.join(T, "ghfail")
CACHE = os.path.join(HOME, ".cache")
t = h.Tests("status line")

# The mock: one "<STATE> <number>" per line of $MOCK_PR becomes the JSON gh prints; $MOCK_GH_FAIL makes it fail.
MOCK_GH = f"""#!{sys.executable}
import json, os, sys
with open(os.environ["MOCK_GH_CALLS"], "a") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\\n")
if os.path.exists(os.environ["MOCK_GH_FAIL"]):
    sys.exit(1)
rows = [ln.split() for ln in open(os.environ["MOCK_PR"]).read().splitlines() if ln.strip()]
print(json.dumps([{{"state": s, "number": int(n)}} for s, n in rows]))
"""


def environment(**extra: str) -> dict[str, str]:
    return h.env(HOME, **{"PATH": f"{BIN}:{os.environ['PATH']}", "MOCK_PR": PRS, "MOCK_GH_FAIL": FAIL, "MOCK_GH_CALLS": CALLS,
                          "AGENT_FABRIC_STATUSLINE_PR_TTL": "0", **extra})


def line_of(session: dict | str, cwd: str | None = None, **extra: str) -> h.Result:
    text = session if isinstance(session, str) else json.dumps(session)
    return h.run(ENTRY, text, environment(**extra), cwd=cwd)


def session(directory: str, **over) -> dict:
    return {"workspace": {"current_dir": directory}, "model": {"display_name": "M"}, **over}


def git(repo: str, *args: str) -> str:
    p = subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
                       env=environment(), capture_output=True, text=True, timeout=60)
    if p.returncode:
        sys.exit(f"test: fixture setup failed: git {' '.join(args)}\n{p.stderr}")
    return p.stdout.strip()


def prs(*rows: str) -> None:
    with open(PRS, "w", encoding="utf-8") as fh:
        fh.write("".join(f"{r}\n" for r in rows))


def calls() -> str:
    try:
        with open(CALLS, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def reset() -> None:
    shutil.rmtree(CACHE, ignore_errors=True)
    for p in (CALLS, FAIL):
        if os.path.exists(p):
            os.unlink(p)
    prs()


def main() -> int:
    os.makedirs(BIN)
    os.makedirs(HOME)
    gh = os.path.join(BIN, "gh")
    with open(gh, "w", encoding="utf-8") as fh:
        fh.write(MOCK_GH)
    os.chmod(gh, 0o755)
    agent = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
    host = socket.gethostname().split(".")[0]
    who = f"👤 {agent}@{host}"

    repo = os.path.join(T, "clone")
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "commit", "-q", "--allow-empty", "-m", "one")
    # A fork clone: origin is the fork, upstream the project it came from, which gh's default would pick (agent-fabric #109).
    git(repo, "remote", "add", "origin", "git@github.com:fork-org/proj.git")
    git(repo, "remote", "add", "upstream", "https://github.com/up-org/proj.git")

    t.group("the branch and pull-request segments")
    reset()
    r = line_of(session(repo))
    t.check("inside a repository, no pull request: 🔀 N/A before the folder, then the branch", r.out.endswith("🔀 N/A 📁 clone 🌿 main"), r.out)
    t.check("the whole line, byte for byte: no trailing newline, nothing on stderr, exit 0",
            r.out == f"[M] {who} 🔀 N/A 📁 clone 🌿 main" and r.err == "" and r.rc == 0, f"{r.out!r} {r.err!r} {r.rc}")
    t.check("a fork clone asks about origin's repository, never upstream's", "--repo fork-org/proj" in calls() and "up-org" not in calls(), calls())
    t.check("gh is asked for the branch's pull requests of any state", "pr list --repo fork-org/proj --head main --state all" in calls(), calls())
    prs("OPEN 386")
    r = line_of(session(repo))
    t.check("an open pull request: 🔀 #386 before the folder", r.out.endswith("🔀 #386 📁 clone 🌿 main"), r.out)
    prs("MERGED 386")
    t.check("a merged pull request: ✅ #386 (the branch is done)", line_of(session(repo)).out.endswith("✅ #386 📁 clone 🌿 main"))
    prs("CLOSED 386")
    t.check("a closed pull request: 🚫 #386", line_of(session(repo)).out.endswith("🚫 #386 📁 clone 🌿 main"))
    prs("MERGED 380", "OPEN 386")
    t.check("an open PR wins over an older merged one on the same branch", "🔀 #386 📁" in line_of(session(repo)).out)
    prs("CLOSED 381", "MERGED 380")
    t.check("with none open, the first listed wins", "🚫 #381 📁" in line_of(session(repo)).out)

    t.group("a pull request nobody could read is unknown, never N/A")
    prs()
    open(FAIL, "w").close()
    t.check("gh failing: #? (unknown), never N/A", "🔀 #? 📁 clone" in line_of(session(repo)).out)
    os.unlink(FAIL)
    shutil.rmtree(CACHE, ignore_errors=True)
    prs("OPEN 386")
    open(FAIL, "w").close()
    t.check("gh failing, with a TTL: still unknown", "🔀 #? 📁 clone" in line_of(session(repo), AGENT_FABRIC_STATUSLINE_PR_TTL="300").out)
    os.unlink(FAIL)
    t.check("an unknown is not cached: the next draw, inside the TTL, asks again", "🔀 #386 📁" in line_of(session(repo), AGENT_FABRIC_STATUSLINE_PR_TTL="300").out)
    open(FAIL, "w").close()
    t.check("within the TTL the cached answer is drawn and gh is not asked", "🔀 #386 📁" in line_of(session(repo), AGENT_FABRIC_STATUSLINE_PR_TTL="300").out)
    git(repo, "checkout", "-q", "-b", "other")
    t.check("the cache is per branch: another branch asks again, and fails to unknown", "🔀 #? 📁 clone 🌿 other" in line_of(session(repo), AGENT_FABRIC_STATUSLINE_PR_TTL="300").out)
    git(repo, "checkout", "-q", "main")
    reset()
    git(repo, "remote", "set-url", "origin", "https://example.com/fork-org/proj.git")
    r = line_of(session(repo), GH_REPO="")
    t.check("no repository named: #?, and gh is not asked", "🔀 #? 📁 clone" in r.out and calls() == "", f"{r.out} / {calls()}")
    for url in ("https://github.com/o-rg/pro.j.git", "https://github.com/o-rg/pro.j", "ssh://git@github.com/o-rg/pro.j.git", "git@github.com:o-rg/pro.j.git"):
        reset()
        git(repo, "remote", "set-url", "origin", url)
        line_of(session(repo))
        t.check(f"origin {url} names o-rg/pro.j", "--repo o-rg/pro.j " in calls(), calls())
    reset()
    git(repo, "remote", "set-url", "origin", "git@github.com:fork-org/proj.git")
    line_of(session(repo), GH_REPO="env-org/env-repo")
    t.check("GH_REPO names the repository over origin", "--repo env-org/env-repo " in calls() and "fork-org" not in calls(), calls())

    t.group("no gh at all")
    reset()
    no_gh = h.tool_dir(os.path.join(T, "no-gh"), ["bash", "git", "jq", "id", "hostname", "dirname", "readlink", "basename", "cat", "timeout", "python3",
                                                  "sha256sum", "cut", "sed", "stat", "date", "mkdir", "env"])
    r = h.run(ENTRY, json.dumps(session(repo)), environment(PATH=no_gh))
    t.check("gh missing: #? (unknown), and the line is still drawn", r.rc == 0 and "🔀 #? 📁 clone 🌿 main" in r.out, f"{r.rc} {r.out}")

    t.group("the ref segment")
    reset()
    git(repo, "remote", "set-url", "origin", "git@github.com:fork-org/proj.git")
    git(repo, "checkout", "-q", "--detach", "main")
    sha = git(repo, "rev-parse", "--short", "HEAD")
    r = line_of(session(repo))
    t.check("a detached HEAD: a link and its short SHA, no branch icon and no pull-request segment",
            r.out.endswith(f"📁 clone 🔗 {sha}") and "🔀" not in r.out and "N/A" not in r.out, r.out)
    t.check("…and no branch icon on a detached HEAD", "🌿" not in r.out, r.out)
    t.check("…and gh is not asked about a detached HEAD", calls() == "", calls())
    plain = os.path.join(T, "projects")
    os.makedirs(plain)
    r = line_of(session(plain))
    t.check("outside a repository: no ref segment and no pull-request segment",
            r.out.endswith("📁 projects") and not any(s in r.out for s in ("🌿", "🔗", "🔀")), r.out)
    unborn = os.path.join(T, "fresh")
    os.makedirs(unborn)
    git(unborn, "init", "-q", "-b", "main")
    git(unborn, "remote", "add", "origin", "https://github.com/fork-org/fresh.git")
    r = line_of(session(unborn))
    t.check("a repository with no commit yet: still its branch name, and N/A for the pull request", r.out.endswith("🔀 N/A 📁 fresh 🌿 main"), r.out)
    t.check("…and the word 'detached' appears nowhere", "detached" not in r.out, r.out)
    sub = os.path.join(repo, "sub")
    os.makedirs(sub)
    git(repo, "checkout", "-q", "main")
    t.check("from a subdirectory the folder is the repository's top level", line_of(session(sub)).out.endswith("📁 clone 🌿 main"))

    t.group("the leading bracket: version · model · effort, each only when sent")
    reset()
    full = session(repo, version="1.2.3", effort={"level": "high"})
    t.check("the bracket reads the bare version · model · effort, in that order", line_of(full).out.startswith("[1.2.3 · M · high] 👤 "), line_of(full).out)
    t.check("no effort block in the JSON: version · model, and no level is invented", line_of(session(repo, version="1.2.3")).out.startswith("[1.2.3 · M] 👤 "))
    t.check("neither version nor effort sent: the model alone", line_of(session(repo)).out.startswith("[M] 👤 "))
    t.check("an effort block with no level shows none", line_of(session(repo, effort={})).out.startswith("[M] 👤 "))

    t.group("a thin payload")
    r = line_of("{}", cwd=plain)
    t.check("no model, no workspace: the model reads Claude and the folder is $PWD", r.rc == 0 and r.out == f"[Claude] {who} 📁 projects", f"{r.rc} {r.out!r}")
    r = line_of({"model": {"display_name": "M"}}, cwd=repo)
    t.check("a payload without a workspace takes $PWD's repository", r.out.endswith("📁 clone 🌿 main"), r.out)
    return t.finish()


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(T, ignore_errors=True)

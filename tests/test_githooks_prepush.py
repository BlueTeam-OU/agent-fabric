#!/usr/bin/env python3
"""The oracle for policies/githooks/pre-push: a project whose arm.json has a
`direct` block lets the holder of its role push straight to the default
branch, and only a change outside direct.pr_paths. Every push here is a real
`git push` to a bare repository with the hook installed, so what git feeds
the hook (arguments, stdin lines) is what the cases assert on.

The role is read from the runtime binding through runtime/identity.py, so a
throwaway AGENT_FABRIC_STATE_DIR is the whole fixture; the project comes
from a .agent-fabric-project marker, the registry and arm.json from a
fixture operator tree (AGENT_FABRIC_OPERATOR).

Exit codes: 0 all checks passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(HERE, "policies", "githooks")
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree, write_json, write_registry  # noqa: E402
own_instance_tree()

T = tempfile.mkdtemp(prefix="test_githooks_prepush.")
STATE = f"{T}/state"
OPERATOR = f"{T}/operator"
REMOTE = f"{T}/remote.git"
REPO = f"{T}/repo"
HOME = f"{T}/home"
os.makedirs(HOME)
LOGIN = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
HOST = subprocess.run(["hostname", "-s"], capture_output=True, text=True, check=True).stdout.strip()
ZERO = "0" * 40

fails = 0
err = ""

DIRECT = {"description": "fixture", "roles": ["brand-comms"],
          "pr_paths": r"^\.claude/|^\.github/|(^|/)package\.json$|^public/.*\.js$|key",
          "cases": [".claude/settings.json", "package.json"]}


def check(label: str, good: bool, detail: str = "") -> None:
    global fails
    if good:
        print(f"  ok   {label}")
        return
    fails += 1
    print(f"  FAIL {label}: {detail}")


def env() -> dict:
    e = {k: v for k, v in os.environ.items()
         if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "CLAUDE_", "GZCOORD_", "GIT_", "XDG_")) and k != "CLAUDECODE"}
    e.update(HOME=HOME, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null",
             AGENT_FABRIC_STATE_DIR=STATE, AGENT_FABRIC_OPERATOR=OPERATOR)
    return e


def git(*args: str, cwd: str = REPO) -> tuple:
    p = subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=cwd, env=env(),
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def bind(role: str) -> None:
    os.makedirs(f"{STATE}/agents/{LOGIN}", exist_ok=True)
    with open(f"{STATE}/agents/{LOGIN}/binding.json", "w", encoding="utf-8") as f:
        f.write(json.dumps({"agent": LOGIN, "host": HOST, "role": role or None, "project": "demo",
                            "working_copy": None, "updated_at": "x"}) + "\n")


def put(rel: str, content: str) -> None:
    p = f"{REPO}/{rel}"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(content)


def commit(*rels: str) -> None:
    for r in rels:
        put(r, "x\n")
    git("add", "-A")
    rc, _, e = git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "c")
    assert rc == 0, e


def fixture(project: str) -> None:
    """A repo of `project` with one commit on main already pushed to the bare remote."""
    shutil.rmtree(REPO, ignore_errors=True)
    shutil.rmtree(REMOTE, ignore_errors=True)
    git("init", "-q", "--bare", "-b", "main", REMOTE, cwd=T)
    os.makedirs(REPO)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@e")
    git("config", "user.name", "t")
    git("config", "core.hooksPath", HOOKS)
    git("remote", "add", "origin", REMOTE)
    with open(f"{REPO}/.git/info/exclude", "a", encoding="utf-8") as f:
        f.write(".agent-fabric-project\n")
    with open(f"{REPO}/.agent-fabric-project", "w", encoding="utf-8") as f:
        f.write(project + "\n")
    commit("content/a.md")
    rc, _, e = git("-c", "core.hooksPath=/dev/null", "push", "-q", "origin", "main")
    assert rc == 0, e


def push(*refspec: str) -> int:
    global err
    rc, _, err = git("push", "-q", "origin", *(refspec or ("main",)))
    return rc


def run() -> None:
    write_registry(f"{OPERATOR}/projects", {"projects": {
        "plain": {"remotes": [], "default_branch": "main"},
        "direct": {"remotes": [], "default_branch": "main"},
    }})
    write_json(f"{OPERATOR}/projects/plain/integration/gh/arm.json", {"boundary": {"paths": "x", "cases": ["x"]}})
    write_json(f"{OPERATOR}/projects/direct/integration/gh/arm.json",
               {"boundary": {"paths": "x", "cases": ["x"]}, "direct": DIRECT})

    print("a project without a direct block is not touched")
    bind("backend-dev"); fixture("plain")
    commit(".claude/settings.json")
    check("push to main passes, in silence", push() == 0 and err.strip() == "", err)

    print("a managed project with no arm.json at all is not direct")
    bind("backend-dev"); fixture("plain")
    os.remove(f"{OPERATOR}/projects/plain/integration/gh/arm.json")
    commit(".claude/settings.json")
    check("push to main passes", push() == 0, err)
    write_json(f"{OPERATOR}/projects/plain/integration/gh/arm.json", {"boundary": {"paths": "x", "cases": ["x"]}})

    print("a direct project, the named role")
    bind("brand-comms"); fixture("direct")
    commit("content/b.md", "src/pages/index.astro")
    check("a content-only change goes straight to main", push() == 0, err)
    commit("src/ok.md", "public/img/a.png")
    commit("package.json")
    check("a pr_paths file anywhere in the pushed range is refused", push() == 1, "admitted")
    check("…naming the file and the rule", "package.json" in err and "ADR-019" in err and "pull request" in err, err)
    check("…and nothing reached the remote", git("rev-parse", "main", cwd=REMOTE)[1].strip()
          != git("rev-parse", "main")[1].strip(), "main moved")

    bind("brand-comms"); fixture("direct")
    commit("public/vendor/lib.js")
    check("executable vendor JavaScript is refused", push() == 1 and "public/vendor/lib.js" in err, err)
    bind("brand-comms"); fixture("direct")
    commit("content/api-key-guide.md")
    check("a secret-shaped word in a path is refused", push() == 1 and "api-key-guide" in err, err)
    bind("brand-comms"); fixture("direct")
    commit("package.json")
    git("-c", "core.hooksPath=/dev/null", "revert", "--no-edit", "HEAD")
    check("a change that is reverted inside the push leaves no PR path and passes", push() == 0, err)

    print("a direct project, any other role")
    bind("backend-dev"); fixture("direct")
    commit("content/b.md")
    check("refused even for a content change", push() == 1, "admitted")
    check("…saying the direct push is that role's and the rest is a PR",
          "brand-comms" in err and "pull request" in err and "backend-dev" in err, err)
    bind(""); fixture("direct")
    commit("content/b.md")
    check("no role bound: refused", push() == 1 and "no role bound" in err, err)

    print("other refs and deletions")
    bind("backend-dev"); fixture("direct")
    commit(".claude/settings.json", "package.json")
    check("a push to a feature branch passes whatever it changes", push("main:refs/heads/feat/x") == 0, err)
    bind("brand-comms"); fixture("direct")
    check("deleting main is refused", push(":main") == 1 and "deleting main" in err, err)
    bind("backend-dev")
    check("…also for another role's session", push(":main") == 1, err)
    bind("brand-comms")
    push("main:refs/heads/feat/y")
    check("deleting another branch passes", push(":feat/y") == 0, err)

    print("a new default branch on the remote (all-zero remote sha)")
    bind("brand-comms"); fixture("direct")
    # The remote lost main, the local clone still tracks it: what a new main
    # adds is measured from refs/remotes/origin/main.
    shutil.rmtree(REMOTE); git("init", "-q", "--bare", "-b", "seed", REMOTE, cwd=T)
    commit("content/new.md")
    check("content-only: passes", push() == 0, err)
    bind("brand-comms"); fixture("direct")
    shutil.rmtree(REMOTE); git("init", "-q", "--bare", "-b", "seed", REMOTE, cwd=T)
    commit(".github/workflows/ci.yml")
    check("a PR path since the merge base: refused", push() == 1 and ".github/workflows/ci.yml" in err, err)
    bind("brand-comms"); fixture("direct")
    shutil.rmtree(REMOTE); git("init", "-q", "--bare", "-b", "seed", REMOTE, cwd=T)
    git("update-ref", "-d", "refs/remotes/origin/main")
    check("no remote-tracking main to measure from: refused, never guessed",
          push() == 1 and "merge base" in err, err)

    print("a broken arm.json of a direct project fails closed")
    bind("brand-comms"); fixture("direct")
    commit("content/b.md")
    with open(f"{OPERATOR}/projects/direct/integration/gh/arm.json", "w", encoding="utf-8") as f:
        f.write("{not json")
    check("unreadable arm.json: refused with the reason", push() == 1 and "arm.json" in err, err)
    write_json(f"{OPERATOR}/projects/direct/integration/gh/arm.json",
               {"boundary": {"paths": "x", "cases": ["x"]}, "direct": {**DIRECT, "pr_paths": "("}})
    check("a pr_paths that does not compile: refused", push() == 1 and "direct is not usable" in err, err)

    print("a working copy that is no managed project")
    bind("backend-dev"); fixture("direct")
    os.remove(f"{REPO}/.agent-fabric-project")
    commit(".claude/settings.json")
    check("passes", push() == 0, err)


try:
    run()
finally:
    shutil.rmtree(T, ignore_errors=True)
print(f"{fails} failed" if fails else "all passed")
sys.exit(1 if fails else 0)
